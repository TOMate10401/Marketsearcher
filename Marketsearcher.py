import requests
from bs4 import BeautifulSoup
import streamlit as st


def vinted_scrape(search_term):
    url = "https://www.vinted.de/catalog?search_text="

    
    size = {"XS" : "206", "S" : "207", "M" : "208", "L" : "209", "XL" : "210", "XXL" : "211"}
    gender = {"male" : "5", "female" : "1904"}
    condition = {"neu" : "6", "wie neu" : "1", "sehr gut" : "2", "gut" : "3", "gebraucht" : "4"}
    color = {}

    term = search_term["term"].strip().replace(" ", "+")
    url = url + term

    if search_term["gender"] != "":
        url += "&catalog[]=" + gender[search_term["gender"]]

    if search_term["size"] != "":
        for x in search_term["size"]:
            url += "&size_ids[]=" + size[x]

    if search_term["condition"] != "":
        for x in search_term["condition"]:
            url += "&status_ids[]=" + condition[x]

    if search_term["min_price"] != "":
        url += "&price_from=" + search_term["min_price"]

    if search_term["max_price"] != "":
        url += "&price_to=" + search_term["max_price"]

    #&price_from=5&currency=EUR&price_to=50



    

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    page = requests.get(url, headers=headers)
    
    soup = BeautifulSoup(page.text, features="lxml")

    items = soup.find_all('div', class_="feed-grid__item")


    vinted_items = []

    for item in items:
        item_dict = {}

        product_id = item.find("div", {"data-testid": lambda x: x and x.startswith("product-item-id-")})["data-testid"].split("-")[-1]

        # Produkt-ID
        item_dict["product_id"] = product_id

        # Titel
        item_dict["title"] = item.find("p", {"data-testid": f"product-item-id-{product_id}--description-title"}).text.strip()

        # Preis
        item_dict["price"] = item.find("p", {"data-testid": f"product-item-id-{product_id}--price-text"}).text.strip()

        # Zustand
        item_dict["condition"] = item.find("p", {"data-testid": f"product-item-id-{product_id}--description-subtitle"}).text.strip()

        # Link
        item_dict["link"] = item.find("a", {"data-testid": f"product-item-id-{product_id}--overlay-link"})["href"]

        # Bild-URL
        item_dict["image_url"] = item.find("img", {"data-testid": f"product-item-id-{product_id}--image--img"})["src"]


        vinted_items.append(item_dict)
    
    return vinted_items


def ebay_scrape(term):
    url = "https://www.ebay.de/sch/i.html?_nkw=" #&LH_SellerType=1

    term = term.strip().replace(" ", "+")

    url = url + term

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    page = requests.get(url, headers=headers)
    print(page.status_code)
    soup = BeautifulSoup (page.text, features="lxml")


def kleinanzeigen_scraper(term):


    return


def main():
    search_term = {}

    st.title("Marketplace")

    search_term["term"] = st.text_input("Suchbegriff", "")
    search_term["gender"] = st.selectbox("Gender: ", ("", "male", "female"))
    #search_term["brand"] = st.text_input("Marke", "")
    search_term["size"] = st.multiselect("Größe: ", ("XS", "S", "M", "L", "XL", "XXL"))
    search_term["condition"] = st.multiselect("Zustand: ", ("neu", "wie neu", "sehr gut", "gut", "gebraucht"))
    search_term["min_price"] = st.text_input("Mindestpreis", "")
    search_term["max_price"] = st.text_input("Maximalpreis", "")



    
    items = vinted_scrape(search_term)

    #option = st.selectbox("sortieren nach: ", ("Preis auf", "Preis ab", "Titel"))
    #if option == "Preis auf":
    #    items = items = sorted(items, key=lambda d: d["price"])

    for item in items:
        st.subheader(item["title"])
        st.write(f"Zustand: {item['condition']}")
        st.write(f"Preis: {item['price']}")
        st.write(f"Link: {item['link']}")
        st.image(item["image_url"])
        st.divider()


if __name__ == "__main__":
    main()