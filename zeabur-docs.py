import requests
import re
import xml.etree.ElementTree as ET
import json
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
import ast


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
            r"\{[^}]*locale:\s*'([^']+)',\s*name:\s*'([^']+)'\s*\}", language_array
        )

        language_list = [{"locale": locale, "name": name} for locale, name in languages]
        return language_list


def fix_keys(content):
    return re.sub(r'(?<!["\'])\b(\w+)\b(?=\s*:)', r'"\1"', content)


def strip_ts_line_comments(ts_content):
    """Remove full-line // comments; zeabur _meta.ts uses these and ast.literal_eval cannot parse them."""
    lines = []
    for line in ts_content.splitlines():
        if line.strip().startswith("//"):
            continue
        lines.append(line)
    return "\n".join(lines)


def slug_to_title(slug):
    return " ".join(part.capitalize() for part in slug.split("-"))


def category_label(meta_key, value):
    """Map _meta entry to sidebar bucket name; skip separators."""
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return None
    if value.get("type") == "separator":
        return None
    if "title" in value:
        return value["title"]
    if value.get("display") == "hidden":
        return slug_to_title(meta_key)
    return value.get("title") or slug_to_title(meta_key)


def build_temp_urls(root_meta):
    temp_urls = {}
    for meta, val in root_meta.items():
        label = category_label(meta, val)
        if label is None:
            continue
        if isinstance(val, dict) and "href" in val and "title" in val:
            temp_urls[label] = {val["title"]: val.get("href", "")}
        else:
            temp_urls[label] = {}
    return temp_urls


def get_root_meta(locale):
    root_meta_url = f"https://raw.githubusercontent.com/zeabur/zeabur/refs/heads/main/docs/pages/{locale}/_meta.ts"
    response = requests.get(root_meta_url)
    ts_content = response.text
    cleaned_content = strip_ts_line_comments(ts_content)
    cleaned_content = cleaned_content.replace("export default ", "").strip()
    cleaned_content = cleaned_content.replace("'", '"')
    cleaned_content = fix_keys(cleaned_content)
    root_meta = ast.literal_eval(cleaned_content)
    return json.dumps(root_meta, ensure_ascii=False, indent=2)


def get_sitemap_urls():
    sitemap_url = "https://zeabur.com/docs/sitemap.xml"
    response = requests.get(sitemap_url)
    sitemap_xml = response.text

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
        root_meta = json.loads(root_meta)
        temp_urls = build_temp_urls(root_meta)

        for url in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc"):
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
            label = category_label(meta, root_meta[meta])
            if label is not None and label in temp_urls:
                temp_urls[label][title] = url
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

def sort_docs_json():
    with open("zeabur-docs.json", "r") as f:
        data = json.load(f)

    sorted_data = {}
    for locale, categories in data.items():
        sorted_categories = {}
        for category, pages in categories.items():
            if isinstance(pages, dict):
                sorted_pages = dict(sorted(pages.items()))
                sorted_categories[category] = sorted_pages
            else:
                sorted_categories[category] = pages
        sorted_data[locale] = sorted_categories

    with open("zeabur-docs.json", "w") as f:
        json.dump(sorted_data, f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    generate_docs_language_json()
    generate_docs_json()
    sort_docs_json()
