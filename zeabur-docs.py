import requests
import re
import xml.etree.ElementTree as ET
import json
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor


def get_docs_languages():
    language_url = (
        "https://raw.githubusercontent.com/zeabur/zeabur/main/docs/theme.config.js"
    )
    response = requests.get(language_url)
    language_js = response.text

    match = re.search(r"i18n:\s*\[(.*?)\]", language_js, re.DOTALL)
    if match:
        language_array = match.group(1)
        languages = re.findall(
            r"\{[^}]*locale:\s*'([^']+)',\s*text:\s*'([^']+)'\s*\}", language_array
        )

        language_list = [{"locale": locale, "text": text} for locale, text in languages]
        return language_list


def get_root_meta(locale):
    root_meta_url = f"https://raw.githubusercontent.com/zeabur/zeabur/main/docs/pages/_meta.{locale}.json"
    response = requests.get(root_meta_url)
    root_meta = response.json()
    return root_meta


def get_sitemap_urls():
    sitemap_url = "https://zeabur.com/docs/sitemap.xml"
    response = requests.get(sitemap_url)
    sitemap_xml = response.content

    root = ET.fromstring(sitemap_xml)
    docs_languages = get_docs_languages()

    with ThreadPoolExecutor() as executor:
        root_metas = list(
            executor.map(
                get_root_meta, [language["locale"] for language in docs_languages]
            )
        )

    urls = {}
    all_urls = []

    for language, root_meta in zip(docs_languages, root_metas):
        temp_urls = {root_meta[meta]: {} for meta in root_meta}

        for url in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc"):
            if language["locale"] == "en-US":
                check = True
                for l in docs_languages:
                    if l["locale"] in url.text:
                        check = False
                        break
                if check:
                    all_urls.append((url.text, root_meta, temp_urls))
            else:
                if language["locale"] in url.text:
                    all_urls.append((url.text, root_meta, temp_urls))

        urls[language["locale"]] = temp_urls

    with ThreadPoolExecutor() as executor:
        executor.map(process_url, all_urls)

    return urls


def process_url(params):
    url, root_meta, temp_urls = params
    title = get_docs_content(url)
    for meta in root_meta:
        if meta in url:
            temp_urls[root_meta[meta]][title] = url
            break


def get_docs_content(url):
    try:
        print(f"Fetching {url}")
        response = requests.get(url)
        html = response.text
        soup = BeautifulSoup(html, "html.parser")
        title = ""

        h1_tag = soup.find("h1")
        h2_tag = soup.find("h2")
        h3_tag = soup.find("h3")

        if h1_tag:
            title = h1_tag.text
        elif h2_tag:
            title = h2_tag.text
        elif h3_tag:
            title = h3_tag.text

        return title
    except requests.RequestException as e:
        print(f"Failed to fetch {url}: {e}")
        return "Error"


def generate_docs_language_json():
    urls = get_docs_languages()
    with open("zeabur-docs-language.json", "w") as f:
        json.dump(urls, f, indent=4, ensure_ascii=False)


def generate_docs_json():
    urls = get_sitemap_urls()
    with open("zeabur-docs.json", "w") as f:
        json.dump(urls, f, indent=4, ensure_ascii=False)


if __name__ == "__main__":
    generate_docs_language_json()
    generate_docs_json()
