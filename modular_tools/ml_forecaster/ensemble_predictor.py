"""
Modular Tools — Ensemble Predictor
Generalized, reusable manager for Layer 2 Prophet time-series models
and Layer 3 XGBoost tabular regression models. Not specific to flights.
"""

import os
import pickle
import math
import time
from loguru import logger

# Lazy/Safe imports
PROPHET_AVAILABLE = False
XGBOOST_AVAILABLE = False

try:
    from prophet import Prophet
    import pandas as pd
    PROPHET_AVAILABLE = True
except ImportError:
    logger.warning("Prophet library not available. Prophet model runs will use math fallback.")

try:
    import xgboost as xgb
    import numpy as np
    import pandas as pd
    XGBOOST_AVAILABLE = True
except ImportError:
    logger.warning("XGBoost library not available. XGBoost model runs will use tree fallback.")


class ReusableEnsemblePredictor:
    def __init__(self, models_dir: str):
        self.models_dir = models_dir
        os.makedirs(self.models_dir, exist_ok=True)

    # ═══════════════════════════════════════════════
    # PROPHET TIME-SERIES MODEL MANAGEMENT
    # ═══════════════════════════════════════════════

    async def run_prophet_forecast(self, model_id: str, historical_df, forecast_periods: int = 30) -> dict:
        """
        Trains or loads a cached Prophet model for a specific key (model_id)
        and predicts future points.
        `historical_df` must have columns 'ds' (datetime/string) and 'y' (float).
        """
        model_path = os.path.join(self.models_dir, f"prophet_{model_id}.pkl")
        model = None

        # Check if cache exists and is relatively fresh (under 7 days)
        if os.path.exists(model_path):
            file_age = time.time() - os.path.getmtime(model_path)
            if file_age < 604800: # 7 days
                try:
                    with open(model_path, "rb") as f:
                        model = pickle.load(f)
                    logger.info(f"Loaded cached Prophet model: {model_path}")
                except Exception as e:
                    logger.warning(f"Failed to load cached Prophet model: {e}")

        # Train new model if needed
        if model is None:
            if PROPHET_AVAILABLE:
                model = self._train_prophet(historical_df, model_path)
            else:
                logger.warning("Prophet not installed. Using mathematical smoothing fallback.")

        # Run inference
        if model and PROPHET_AVAILABLE:
            try:
                import pandas as pd
                # Run forecast
                future = model.make_future_dataframe(periods=forecast_periods)
                forecast = model.predict(future)
                
                # Extract results
                latest = forecast.iloc[-1]
                mid_term = forecast.iloc[-int(forecast_periods / 2)] if len(forecast) > int(forecast_periods / 2) else latest
                short_term = forecast.iloc[-int(forecast_periods / 4)] if len(forecast) > int(forecast_periods / 4) else latest
                
                return {
                    "forecast_short": float(short_term.get("yhat", latest["yhat"])),
                    "forecast_mid": float(mid_term.get("yhat", latest["yhat"])),
                    "forecast_long": float(latest.get("yhat", latest["yhat"])),
                    "confidence_band": {
                        "low": float(latest.get("yhat_lower", latest["yhat"] * 0.9)),
                        "high": float(latest.get("yhat_upper", latest["yhat"] * 1.1))
                    },
                    "source": "PROPHET"
                }
            except Exception as e:
                logger.error(f"Prophet forecast execution failed: {e}")

        # Fallback math prediction
        return self._run_math_smoothing_fallback(historical_df, forecast_periods)

    def _train_prophet(self, historical_df, model_path: str):
        """Fits a Prophet model and dumps to pickle."""
        try:
            import pandas as pd
            # Format check
            df = pd.DataFrame(historical_df)
            df.columns = ["y", "ds"]
            df["ds"] = pd.to_datetime(df["ds"])

            # Fit Prophet
            m = Prophet(yearly_seasonality=True, weekly_seasonality=True, daily_seasonality=False)
            m.fit(df)

            with open(model_path, "wb") as f:
                pickle.dump(m, f)
            logger.info(f"Saved trained Prophet model to {model_path}")
            return m
        except Exception as e:
            logger.error(f"Failed to train Prophet model: {e}")
            return None

    def _run_math_smoothing_fallback(self, historical_df, periods: int) -> dict:
        """Pure math double exponential smoothing fallback if Prophet is not installed."""
        if historical_df is None or len(historical_df) == 0:
            return {
                "forecast_short": 5000.0,
                "forecast_mid": 4800.0,
                "forecast_long": 4600.0,
                "confidence_band": {"low": 4000.0, "high": 5200.0},
                "source": "MATH_FALLBACK"
            }

        # Expect historical_df to be list of dicts or list of prices
        prices = []
        if isinstance(historical_df, list):
            if len(historical_df) > 0 and isinstance(historical_df[0], dict):
                prices = [float(h.get("y", h.get("price", 5000))) for h in historical_df]
            else:
                prices = [float(x) for x in historical_df]
        else: # Pandas series/df
            try:
                prices = historical_df["y"].tolist()
            except Exception:
                prices = [5000.0]

        current = prices[-1]
        
        # Calculate trend line
        if len(prices) > 5:
            recent_avg = sum(prices[-5:]) / 5.0
            older_avg = sum(prices[-15:-5]) / 10.0 if len(prices) > 15 else sum(prices[:5]) / 5.0
            slope = (recent_avg - older_avg) / (10.0 if len(prices) > 15 else max(1.0, len(prices) - 5))
        else:
            slope = 0.0

        # Predict future steps with attenuation
        p_short = current + slope * (periods / 4) * 0.8
        p_mid = current + slope * (periods / 2) * 0.6
        p_long = current + slope * periods * 0.4

        # Bounds based on variance
        mean = sum(prices) / len(prices)
        variance = sum((x - mean) ** 2 for x in prices) / len(prices)
        std_dev = max(100.0, math.sqrt(variance))

        return {
            "forecast_short": round(max(500.0, p_short), 2),
            "forecast_mid": round(max(500.0, p_mid), 2),
            "forecast_long": round(max(500.0, p_long), 2),
            "confidence_band": {
                "low": round(max(500.0, p_long - 1.5 * std_dev), 2),
                "high": round(p_long + 1.5 * std_dev, 2)
            },
            "source": "MATH_FALLBACK"
        }

    # ═══════════════════════════════════════════════
    # XGBOOST TABULAR MODEL MANAGEMENT
    # ═══════════════════════════════════════════════

    async def train_xgboost_regressor(self, model_id: str, training_data: list, target_col: str, feature_cols: list) -> bool:
        """
        Trains and saves a global or group-specific XGBoost regression model.
        `training_data` is a list of dictionaries.
        """
        if not XGBOOST_AVAILABLE:
            logger.warning("XGBoost library unavailable. Cannot train regressor.")
            return False

        try:
            import pandas as pd
            import numpy as np
            import xgboost as xgb

            df = pd.DataFrame(training_data)
            y = df[target_col].astype(float)
            X = df[feature_cols].astype(float)

            # Detect GPU availability
            xgb_params = {
                "n_estimators": 100,
                "max_depth": 5,
                "learning_rate": 0.08,
                "random_state": 42
            }
            try:
                test_model = xgb.XGBRegressor(tree_method="hist", device="cuda", n_estimators=1)
                test_model.fit(np.array([[1.0]]), np.array([1.0]))
                xgb_params["tree_method"] = "hist"
                xgb_params["device"] = "cuda"
                logger.info(f"GPU acceleration enabled for XGBoost model {model_id} (device='cuda').")
            except Exception:
                logger.info(f"GPU not available for XGBoost model {model_id}, using CPU (tree_method='hist').")
                xgb_params["tree_method"] = "hist"
                xgb_params["device"] = "cpu"

            # Fit Regressor with parameters
            model = xgb.XGBRegressor(**xgb_params)
            model.fit(X, y)

            # Pickle dump
            model_path = os.path.join(self.models_dir, f"xgboost_{model_id}.pkl")
            with open(model_path, "wb") as f:
                pickle.dump(model, f)
            
            logger.info(f"XGBoost regressor trained and saved successfully: {model_path}")
            return True
        except Exception as e:
            logger.error(f"XGBoost model training failed for {model_id}: {e}")
            return False

    async def predict_xgboost(self, model_id: str, feature_vector: dict, feature_cols: list) -> dict:
        """
        Runs inference on a saved XGBoost model, calculating permutation importance
        deltas as feature drivers.
        """
        model_path = os.path.join(self.models_dir, f"xgboost_{model_id}.pkl")
        model = None

        if os.path.exists(model_path):
            try:
                with open(model_path, "rb") as f:
                    model = pickle.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cached XGBoost model: {e}")

        # If model loaded and XGBoost library available, execute prediction
        if model and XGBOOST_AVAILABLE:
            try:
                import pandas as pd
                # Format feature vector
                x_dict = {col: float(feature_vector.get(col, 0.0)) for col in feature_cols}
                x_df = pd.DataFrame([x_dict])[feature_cols]
                
                prediction = float(model.predict(x_df)[0])
                
                # Perform Permutation Importance fallback for drivers
                drivers = self._calculate_permutation_drivers(model, x_df, feature_cols)
                
                return {
                    "prediction": prediction,
                    "drivers": drivers,
                    "source": "XGBOOST"
                }
            except Exception as e:
                logger.error(f"XGBoost prediction execution failed: {e}")

        # Fallback response with default heuristic drivers for cold starts
        fallback_drivers = [
            {"feature": "days_to_departure", "impact": "PRICE_UP", "magnitude": "HIGH", "delta": 150.0},
            {"feature": "brent_crude_price_usd", "impact": "PRICE_DOWN", "magnitude": "MEDIUM", "delta": -50.0}
        ]
        return {
            "prediction": float(feature_vector.get("current_price", 5000.0)),
            "drivers": fallback_drivers,
            "source": "HEURISTIC_FALLBACK"
        }

    def _calculate_permutation_drivers(self, model, x_df, feature_cols: list) -> list:
        """Calculates features contribution by perturbing inputs sequentially."""
        drivers = []
        try:
            base_pred = float(model.predict(x_df)[0])
            deltas = []
            
            for col in feature_cols:
                perturbed_df = x_df.copy()
                # perturb value
                val = float(perturbed_df[col].iloc[0])
                perturbed_df[col] = val * 1.5 + 1.0
                
                perturbed_pred = float(model.predict(perturbed_df)[0])
                delta = perturbed_pred - base_pred
                deltas.append((col, delta))

            # Sort by absolute impact
            deltas.sort(key=lambda x: abs(x[1]), reverse=True)
            
            for col, d in deltas[:4]:
                impact = "PRICE_UP" if d > 0 else "PRICE_DOWN"
                magnitude = "HIGH" if abs(d) > 200 else "MEDIUM" if abs(d) > 80 else "LOW"
                drivers.append({
                    "feature": col,
                    "impact": impact,
                    "magnitude": magnitude,
                    "delta": round(d, 2)
                })
        except Exception as e:
            logger.debug(f"Permutation drivers calculation failed: {e}")
        
        return drivers
