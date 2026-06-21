from bs4 import BeautifulSoup
import re

def main():
    print("Reading emt_page.html...")
    with open("emt_page.html", "r", encoding="utf-8") as f:
        html = f.read()
        
    soup = BeautifulSoup(html, "lxml")
    
    # Let's search for "QP-1831" (or other flight numbers)
    target = soup.find(string=re.compile("QP-1831|6E-6261|AkasaAir|IndiGo"))
    if not target:
        # Try generic search
        target = soup.find(string=re.compile("BOOK NOW|Book Now"))
        
    if target:
        print("Found target text container!")
        # Trace parents up 5 levels to see their classes and tag names
        parent = target
        level = 0
        while parent and level < 8:
            if hasattr(parent, "get"):
                tag = parent.name
                classes = parent.get("class", [])
                id_val = parent.get("id", "")
                print(f"Level {level}: TAG: {tag} | ID: {id_val} | CLASSES: {classes}")
            parent = parent.parent
            level += 1
            
    # Let's list all elements that have classes containing 'flight' or 'row' or 'card'
    print("\nMatching elements by classes/IDs:")
    for tag in ['div', 'section', 'article']:
        for el in soup.find_all(tag):
            classes = el.get("class", [])
            id_val = el.get("id", "")
            
            class_str = " ".join(classes)
            if any(k in class_str.lower() for k in ['flight-list', 'row-grid', 'flightlist', 'flightcard', 'flight-card']) or 'ResultDiv' in id_val:
                print(f"TAG: {tag} | ID: {id_val} | CLASSES: {classes} | Inner text preview: {repr(el.text[:80].strip())}")

if __name__ == "__main__":
    main()
