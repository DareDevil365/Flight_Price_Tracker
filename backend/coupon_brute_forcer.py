"""Test eligible coupon codes against the selected flight's payable total."""
import asyncio
import math
import time


class CouponNavigationBlocked(ValueError):
    pass


class CouponBruteForcer:
    def __init__(self, platform_worker, financial_filter, log_callback):
        self.worker, self.filter, self.log = platform_worker, financial_filter, log_callback

    async def _wait_total(self, page, expected=None):
        last, stable = None, 0
        for _ in range(25):
            price = await self.worker.parse_current_price(page)
            if not math.isfinite(price) or price <= 0:
                raise ValueError('Invalid checkout total')
            stable = stable + 1 if last is not None and abs(last-price) < 0.01 else 0
            last = price
            if stable >= 3 and (expected is None or abs(price-expected) < 0.01):
                if getattr(self,'context_check',None):
                    await self.context_check()
                return price
            await asyncio.sleep(0.2)
        raise ValueError('Checkout price did not settle or return to baseline')

    async def _check_blocker(self,page):
        check=getattr(self.worker,'coupon_navigation_blocker',None)
        if check:
            reason=await check(page)
            if reason:
                raise CouponNavigationBlocked(reason)

    async def brute_force(self, page, coupons, financial_rules, search_id, db=None, route=None,
            max_tests=None,budget_seconds=420,context_check=None,audit_scope=None):
        from coupon_audit import CouponAudit
        self.audit=None
        self.audit_offers={str(c.get('code','')).upper():c for c in reversed(coupons)}
        self.completed_codes=set()
        scope=audit_scope or {'stage':'unverified'}
        if db is not None and getattr(db,'db',None) is not None:
            self.audit=await CouponAudit.start(db,self.worker.platform_id,search_id,scope)
        try:
            result=await self._run(page,coupons,financial_rules,search_id,db,route,max_tests,budget_seconds,context_check)
            if scope.get('onsite_collection')=='failed':
                result['coverage']['complete']=False
                result['coverage']['collection']='Onsite collection failed; only previously collected codes were considered'
            if self.audit:
                result['audit_run_id']=self.audit.id
                await self.audit.finish('awaiting_checkout_confirmation' if scope.get('stage')=='merchant_payment' else 'review_only',result)
            return result
        except BaseException as exc:
            if self.audit:
                for code,offer in self.audit_offers.items():
                    if code not in self.completed_codes:
                        await self.audit.trial({'code':code,'status':'not_tested',
                            'reason':'Run interrupted; no validated outcome'},offer)
                await self.audit.finish('interrupted' if isinstance(exc,asyncio.CancelledError) else 'failed',
                    {'reason':type(exc).__name__+': '+str(exc)})
            raise
        finally:
            self.audit_offers.clear()

    async def _record(self,results,result):
        results.append(result)
        self.completed_codes.add(result.get('code'))
        if self.audit:
            await self.audit.trial(result,self.audit_offers.get(result.get('code')))

    async def _run(self, page, coupons, financial_rules, search_id, db=None, route=None, max_tests=None,budget_seconds=420,context_check=None):
        self.context_check=context_check
        original_code=await self.worker.get_applied_coupon_code(page)
        original_applied=(await self.worker.check_coupon_applied(page)).get('success')
        if original_applied and not original_code:
            raise ValueError('An existing coupon is applied but its code cannot be read. No payment total was verified.')
        original_total=await self._wait_total(page)
        try:
            result=await self._brute_force(page,coupons,financial_rules,search_id,db,route,max_tests,budget_seconds)
            # Removing a pre-existing promotion is an experiment, not consent to
            # leave the traveller with a more expensive cart. An original code
            # with unknown terms cannot be promoted as an eligible winner, but
            # the original state must still be preserved when it was cheaper.
            if result['best_price'] > original_total + 0.01:
                raise ValueError('Coupon testing could not improve the original payable total; restoring the original booking state')
            return result
        except BaseException:
            # Cover failures/cancellation during the first removal, final winner
            # reapplication and baseline settling, not only individual trials.
            async def restore():
                await self._check_blocker(page)
                await self._clear_to_baseline(page)
                if original_applied:
                    await self.worker.enter_coupon_code(page,original_code)
                    await self.worker.click_apply_coupon(page)
                    check=await self.worker.check_coupon_applied(page)
                    if not check.get('success') or check.get('error') or (check.get('code') and check['code']!=original_code):
                        raise ValueError('Original coupon could not be restored')
                await self._wait_total(page,original_total)
            try:
                await asyncio.shield(asyncio.wait_for(restore(),15))
            except Exception:
                self.log(search_id,self.worker.platform_id,'warning',
                    'Could not restore the original payable total. Recheck the booking page before paying.')
            raise

    async def _clear_to_baseline(self,page,expected=None):
        await self.worker.clear_coupon_field(page)
        total=await self._wait_total(page,expected)
        if (await self.worker.check_coupon_applied(page)).get('success'):
            raise ValueError('The applied coupon was not removed. No coupon-free baseline can be verified.')
        return total

    async def _brute_force(self,page,coupons,financial_rules,search_id,db,route,max_tests,budget_seconds):
        deadline=time.monotonic()+budget_seconds
        original_code = await self.worker.get_applied_coupon_code(page)
        originally_applied = (await self.worker.check_coupon_applied(page)).get('success')
        if originally_applied and not original_code:
            raise ValueError('An existing coupon is applied but its code cannot be read. No payment total was verified.')
        if originally_applied and original_code:
            if not any(isinstance(c.get('code'),str) and c['code'].strip().upper()==original_code for c in coupons):
                from offer_parser import published_offer
                terms=await self.worker.get_coupon_validation_text(page)
                original=published_offer(self.worker.platform_id,original_code,terms,page.url)
                coupons=[{**(original or {'code':original_code}),'eligibility_unconfirmed':not bool(terms)},*coupons]
        if not coupons:
            total = await self._wait_total(page)
            return dict(baseline_price=total,best_price=total,best_coupon=original_code if originally_applied else None,savings=0,all_results=[],
                coverage=dict(eligible=0,tested=0,complete=True))
        baseline = await self._clear_to_baseline(page)
        eligible, results, seen = [], [], set()
        for coupon in coupons:
            from offer_parser import CODE
            raw=coupon.get('code')
            if not isinstance(raw,str) or not CODE.fullmatch(raw.strip().upper()):
                await self._record(results,dict(code=str(raw),status='pre_filtered',reason='Malformed coupon code; no browser interaction'))
                continue
            code = raw.strip().upper()
            if not code or code in seen:
                continue
            seen.add(code)
            coupon={**coupon,'code':code}
            trial_rules={**financial_rules,'booking_total':baseline}
            decision=self.filter.assess(coupon,trial_rules)
            passes, reason = self.filter.passes(coupon, trial_rules)
            if coupon.get('min_booking_value') and baseline < coupon['min_booking_value']:
                passes, reason = False, 'Minimum fare not met'
            if decision.status=='unknown':
                passes=False
            if not passes:
                await self._record(results,dict(code=code, status='conditional' if decision.status=='unknown' else 'pre_filtered', reason=reason))
            else:
                eligible.append(coupon)
        eligible.sort(key=lambda c:(c.get('trust_score') or 0, c.get('discount_value') or 0), reverse=True)
        best, winning = baseline, None
        for index,coupon in enumerate(eligible):
            if time.monotonic()>deadline-20 or (max_tests is not None and index>=max_tests):
                for candidate in eligible[index:]:
                    await self._record(results,dict(code=candidate['code'],status='not_tested',reason='Verification time budget reached; no saving assumed'))
                break
            code = coupon['code']
            await self._check_blocker(page)
            self.log(search_id, self.worker.platform_id, 'info', f'Testing eligible coupon {code}')
            failure_status='error'
            try:
                await self._clear_to_baseline(page,baseline)
                await self.worker.enter_coupon_code(page, code)
                await self.worker.click_apply_coupon(page)
                await self._check_blocker(page)
                accepted = False
                for _ in range(25):
                    check = await self.worker.check_coupon_applied(page)
                    if check.get('error'):
                        failure_status='rejected'
                        raise ValueError(check['error'])
                    if check.get('success'):
                        if check.get('code') and check['code']!=code:
                            raise ValueError('A different coupon is applied; cannot attribute savings to this trial')
                        accepted = True
                        break
                    await asyncio.sleep(0.2)
                if not accepted:
                    failure_status='inconclusive'
                    raise ValueError('No explicit coupon acceptance was found')
                price = await self._wait_total(page)
                terms = await self.worker.get_coupon_validation_text(page)
                if terms:
                    from offer_parser import published_offer
                    actual_offer=published_offer(self.worker.platform_id,code,terms,page.url)
                    actual_decision=self.filter.assess(actual_offer or {'code':code,'eligibility_unconfirmed':True},trial_rules)
                    if actual_decision.status=='unknown':
                        await self._record(results,dict(code=code,status='conditional',price=price,terms=terms,
                            reason='Page accepted this code, but its newly displayed conditions remain unconfirmed'))
                        continue
                if self.filter.contains_violation(terms, trial_rules):
                    await self._record(results,dict(code=code, status='valid_but_excluded', price=price, reason=terms))
                    continue
                if price >= baseline:
                    await self._record(results,dict(code=code,status='accepted_no_saving',price=price,savings=baseline-price,
                        reason='Accepted code did not reduce the payable total'))
                    continue
                await self._record(results,dict(code=code, status='valid_match', price=price, savings=baseline-price, terms=terms))
                if price < best:
                    best, winning = price, code
            except CouponNavigationBlocked as exc:
                await self._record(results,dict(code=code,status='error',reason=str(exc)))
                raise
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self._record(results,dict(code=code, status=failure_status, reason=str(exc)))
                self.log(search_id, self.worker.platform_id, 'warning', f'{code}: {exc}')
            await asyncio.sleep(0.5)
        await self._clear_to_baseline(page,baseline)
        if winning:
            await self._check_blocker(page)
            await self.worker.enter_coupon_code(page, winning)
            await self.worker.click_apply_coupon(page)
            await self._wait_total(page, best)
            check = await self.worker.check_coupon_applied(page)
            if not check.get('success') or check.get('error') or (check.get('code') and check['code']!=winning):
                raise ValueError('Winning coupon could not be confirmed during final verification')
        tested=sum(r['status'] not in ('pre_filtered','not_tested','conditional') or
            (r['status']=='conditional' and 'price' in r) for r in results)
        return dict(baseline_price=baseline,best_price=best,best_coupon=winning,savings=baseline-best,all_results=results,
            coverage=dict(eligible=len(eligible),tested=tested,complete=not any(r['status'] in ('not_tested','conditional','error','inconclusive') for r in results)))
