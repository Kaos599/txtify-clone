import streamlit as st
import requests
from bs4 import BeautifulSoup
import os
import re
import asyncio
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted
from langchain_google_genai import ChatGoogleGenerativeAI
from browser_use import Agent
from urllib.parse import urljoin, urlparse
import platform
import time

load_dotenv()

MIN_CONTENT_LENGTH = 50
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

st.set_page_config(
    page_title="Web Content Extractor Advanced",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
        .subheader {
            font-size: 1.5rem;
            color: #555;
        }
        .content-container {
            padding: 20px;
            border: 1px solid #e1e4e8;
            border-radius: 5px;
            margin-top: 10px;
            background-color: #f8f9fa;
            white-space: pre-line;
        }
        .footer {
            text-align: center;
            padding: 10px;
            color: #777;
            font-size: 0.9em;
        }
    </style>
""", unsafe_allow_html=True)

def clean_text(text: str) -> str:
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^\w\s.,!?-]', '', text)
    text = '\n'.join(line.strip() for line in text.split('\n') if line.strip())
    return text.strip()

async def clean_with_genai(text: str) -> str:
    try:
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        generation_config = {
            "temperature": 0.2,
            "top_p": 0.95,
            "top_k": 32,
            "max_output_tokens": 8192,
        }
        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash-exp",
            generation_config=generation_config,
        )
        prompt = """CLEANING TASK: Clean and format the following web content while:
1. Removing navigation elements, headers, footers, and ads
2. Preserving all meaningful content
3. Maintaining proper paragraph structure
4. Keeping important headings and subheadings
5. Ensuring readability

CONTENT TO CLEAN:
{text}

CLEANED OUTPUT:"""
        response = model.generate_content(prompt.format(text=text))
        if "provide the actual scraped content" in response.text.lower():
            return "CONTENT EXTRACTION ERROR: Failed to retrieve meaningful page content"
        return response.text

    except ResourceExhausted as e:
        error_message = str(e)
        if "429" in error_message or "Resource has been exhausted" in error_message:
            st.warning(f"Gemini API rate limit encountered during cleaning. Please wait a moment and try again. Error: {error_message}")
            return "CLEANING ERROR: API rate limit - please try again later."
        else:
            return f"CLEANING ERROR: {str(e)}"

    except Exception as e:
        return f"CLEANING ERROR: {str(e)}"


async def extract_content_with_agent(url: str) -> tuple[bool, str]:
    llm = ChatGoogleGenerativeAI(
        model='gemini-2.0-flash-exp',
        api_key=os.getenv('GEMINI_API_KEY')
    )

    try:
        agent = Agent(
            task=f"""a. Navigate to {url}
                 b. Wait for page to fully load (5 seconds)
                 c. Extract MAIN CONTENT using CSS selector:
                    body > main, body > article, body > div.content, body
                 d. Fallback to body text if main containers not found""",
            llm=llm,
            max_actions_per_step=4,
        )

        history = await agent.run(max_steps=25)
        result = history.extracted_content()

        full_text_result = "\n".join(result) if isinstance(result, list) else result

        initial_clean = re.sub(
            r'^([🔗🖱️🔍📄].*|Extracted the .*|:)\s*$',
            '',
            full_text_result,
            flags=re.MULTILINE
        ).strip()

        if len(initial_clean) < MIN_CONTENT_LENGTH:
            return False, "Error: Insufficient content extracted"

        final_clean = await clean_with_genai(initial_clean)
        return True, final_clean

    except ResourceExhausted as e:
        error_message = str(e)
        if "429" in error_message or "Resource has been exhausted" in error_message:
            st.warning(f"Gemini API rate limit encountered during content extraction. Please wait a moment and try again. Error: {error_message}")
            return False, "Error: API rate limit - please try again later."
        else:
            return False, f"Error during agent-based extraction: {str(e)}"

    except Exception as e:
        return False, f"Error during agent-based extraction: {str(e)}"
    finally:
        from grpc import aio
        try:
            await aio.shutdown_channel()
        except AttributeError:
            print("Warning: Ignored AttributeError: module 'grpc.aio' has no attribute 'shutdown_channel'")


async def find_linked_pages(url: str, max_pages: int = 5) -> list[dict]:
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        nav_links = []

        nav_tags = soup.find_all('nav')
        if nav_tags:
            for nav in nav_tags:
                nav_links.extend([(a.get('href'), a.text.strip()) for a in nav.find_all('a', href=True)])

        if not nav_links:
            header = soup.find('header')
            footer = soup.find('footer')
            if header:
                nav_links.extend([(a.get('href'), a.text.strip()) for a in header.find_all('a', href=True)])
            if footer:
                nav_links.extend([(a.get('href'), a.text.strip()) for a in footer.find_all('a', href=True)])


        processed_links = []
        base_url_parsed = urlparse(url)
        base_domain = base_url_parsed.netloc

        for link_url, link_text in nav_links:
            absolute_url = urljoin(url, link_url)
            parsed_link_url = urlparse(absolute_url)

            if parsed_link_url.netloc == base_domain and absolute_url not in [item['url'] for item in processed_links]:
                processed_links.append({'url': absolute_url, 'text': link_text})
                if len(processed_links) >= max_pages:
                    break

        return processed_links

    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return []
    except Exception as e:
        print(f"Error finding linked pages with BeautifulSoup: {e}")
        return []


async def process_page(page_url: str) -> tuple[str, str]:
    success, content = await extract_content_with_agent(page_url)
    if success:
        page_title = urlparse(page_url).path.strip('/').replace('/', ' - ') or "Page"
        if not page_title or page_title == "Page":
            page_title = page_url
        return page_title, content
    else:
        return urlparse(page_url).path.strip('/') or "Error Page", f"Error extracting content from {page_url}: {content}"


async def main():
    import asyncio
    import platform

    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    st.markdown("<h1>🌐 Advanced Web Content Extractor</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p class='subheader'>Extract content from web page(s) with AI-powered cleaning</p>",
        unsafe_allow_html=True
    )
    st.markdown(
        "<p style='color: orange;'><b>Note:</b> Frequent use of this tool may encounter API rate limits from Google Gemini. If you experience errors, please wait a few minutes and try again, or reduce the number of pages you are exploring.</p>",
        unsafe_allow_html=True
    )


    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        url = st.text_input(
            "Enter website URL:",
            placeholder="https://example.com",
            help="Paste the main URL of the website you want to explore. **Be aware of potential API rate limits with heavy use.**"
        )
        explore_pages = st.checkbox(
            "Explore Linked Pages",
            value=True,
            help="Check to explore linked pages from the main URL, uncheck to extract only the main page."
        )
        max_pages = st.number_input(
            "Max Pages to Explore:",
            min_value=1,
            max_value=10,
            value=3,
            disabled=not explore_pages,
            help="Maximum number of linked pages to explore from the main URL. Enabled only if 'Explore Linked Pages' is checked. **Exploring more pages increases the chance of hitting API rate limits.**"
        )

        if st.button("🔍 Extract Content", type="primary", use_container_width=True):
            if url:
                if not url.startswith(('http://', 'https://')):
                    url = f'https://{url}'

                all_pages_info = {}
                progress_bar = st.progress(0)
                status_text = st.empty()

                if explore_pages:
                    with st.spinner("Finding linked pages..."):
                        linked_pages = await find_linked_pages(url, max_pages)

                    if linked_pages:
                        num_pages_to_process = len(linked_pages) + 1
                        status_text.markdown(f"Processing 1 of {num_pages_to_process} pages...")

                        tasks = []
                        page_urls = [url] + [page['url'] for page in linked_pages]
                        page_texts = ["Home"] + [page['text'] for page in linked_pages]

                        for i, page_url in enumerate(page_urls):
                            tasks.append(process_page(page_url))

                        results = await asyncio.gather(*tasks)

                        for i, (page_title, content) in enumerate(results):
                            all_pages_info[page_texts[i]] = content
                            progress = int(((i + 1) / num_pages_to_process) * 100)
                            progress_bar.progress(progress)
                            if (i + 1) < num_pages_to_process:
                                status_text.markdown(f"Processing page {i + 2} of {num_pages_to_process}...")
                            else:
                                status_text.markdown("Processing complete!")
                    else:
                        st.warning("No linked pages found on the website. Processing only the main page.")
                        num_pages_to_process = 1
                        tasks = [process_page(url)]
                        page_texts = ["Home"]
                        results = await asyncio.gather(*tasks)
                        page_title, content = results[0]
                        all_pages_info[page_texts[0]] = content
                        num_pages_to_process = 1
                        progress_bar.progress(100)
                        status_text.markdown("Processing complete!")


                else:
                    status_text.markdown("Processing single page...")
                    tasks = [process_page(url)]
                    page_texts = ["Home"]
                    results = await asyncio.gather(*tasks)
                    page_title, content = results[0]
                    all_pages_info[page_texts[0]] = content
                    num_pages_to_process = 1
                    progress_bar.progress(100)
                    status_text.markdown("Processing complete!")


                progress_bar.empty()
                status_text.empty()

                st.markdown("<h3 style='color: #2b5876;'>📑 Extracted Content:</h3>", unsafe_allow_html=True)

                if all_pages_info:
                    page_names = list(all_pages_info.keys())
                    selected_page = st.selectbox("Select Page:", page_names)

                    st.markdown("<div class='content-container'>", unsafe_allow_html=True)
                    st.markdown(all_pages_info[selected_page])
                    st.markdown("</div>", unsafe_allow_html=True)

                    btn_col1, btn_col2, btn_col3 = st.columns([1, 2, 1])
                    with btn_col2:
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        domain = url.split('//')[-1].split('/')[0].replace('.', '_')
                        filename = f"{domain}_{timestamp}_{selected_page.replace(' ', '_')}.txt"

                        st.download_button(
                            label="⬇️ Download Current Page as Text File",
                            data=all_pages_info[selected_page],
                            file_name=filename,
                            mime="text/plain",
                            use_container_width=True
                        )

                else:
                    st.error("No content extracted from the page.")

            else:
                st.warning("⚠️ Please enter a URL")

    st.markdown("---")
    st.markdown("<h3 style='text-align: center; color: #2b5876;'>✨ Features</h3>", unsafe_allow_html=True)
    feat_col1, feat_col2, feat_col3 = st.columns(3)
    with feat_col1:
        st.markdown("""
            ### 🎯 Clean Content
            - Removes ads and clutter
            - Preserves important content
            - Maintains readability
        """)
    with feat_col2:
        st.markdown("""
            ### 🚀 Flexible Extraction
            - Single or Multi-page option
            - AI-powered cleaning
            - Quick processing
        """)
    with feat_col3:
        st.markdown("""
            ### 🛡️ Simple & Secure
            - Easy to use
            - No registration needed
        """)

    st.markdown("---")
    st.markdown(
        "<div class='footer'>Made with ❤️ by Harsh Dayal for Truxt.ai | © 2025</div>",
        unsafe_allow_html=True
    )


if __name__ == '__main__':
    asyncio.run(main())