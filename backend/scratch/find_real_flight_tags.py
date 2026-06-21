from bs4 import BeautifulSoup

def main():
    print("Reading emt_page.html...")
    with open("emt_page.html", "r", encoding="utf-8") as f:
        html = f.read()
        
    soup = BeautifulSoup(html, "lxml")
    
    el = soup.find(id="spnPrice1")
    if el:
        print("\nFound element #spnPrice1:")
        curr = el
        depth = 0
        while curr and depth < 8:
            print(f"  Parent Depth {depth}: TAG: {curr.name} | ID: {curr.get('id')} | CLASSES: {curr.get('class')}")
            curr = curr.parent
            depth += 1
    else:
        print("\n#spnPrice1 not found!")

if __name__ == "__main__":
    main()
