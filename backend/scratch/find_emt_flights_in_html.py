from bs4 import BeautifulSoup, Comment
import re

def main():
    print("Reading emt_page.html...")
    with open("emt_page.html", "r", encoding="utf-8") as f:
        html = f.read()
        
    soup = BeautifulSoup(html, "lxml")
    
    # Search for price texts
    prices = ["5,139", "5,207", "6,033"]
    for price in prices:
        print(f"\nLooking for elements containing price: '{price}'")
        matches = soup.find_all(string=re.compile(price))
        count = 0
        for m in matches:
            if isinstance(m, Comment):
                continue
            parent = m.parent
            if parent.name in ['script', 'style']:
                continue
            count += 1
            print(f"Tag: {parent.name} | Class: {parent.get('class')} | ID: {parent.get('id')} | Text: {repr(m.strip())}")
            
            # Print hierarchy of the first match
            if count == 1:
                curr = parent
                depth = 0
                while curr and depth < 8:
                    print(f"  Parent Depth {depth}: TAG: {curr.name} | ID: {curr.get('id')} | CLASSES: {curr.get('class')}")
                    curr = curr.parent
                    depth += 1
        print(f"Total non-comment/script matches for '{price}': {count}")

if __name__ == "__main__":
    main()
