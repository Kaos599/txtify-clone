import streamlit as st
import requests
from bs4 import BeautifulSoup
import os
import re
import asyncio
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai
from langchain_google_genai import ChatGoogleGenerativeAI
from browser_use import Agent
from urllib.parse import urljoin, urlparse
import platform

load_dotenv()

MIN_CONTENT_LENGTH = 50
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

st.set_page_config(
    page_title="Web Content Extractor",
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
    except Exception as e:
        return f"CLEANING ERROR: {str(e)}"

async def extract_content_with_agent(url: str, navigate_menu_item: str = None) -> tuple[bool, str]:
    llm = ChatGoogleGenerativeAI(
        model='gemini-2.0-flash-exp',
        api_key=os.getenv('GEMINI_API_KEY')
    )

    task_description = ""
    if navigate_menu_item:
        task_description = f"""
            a. Navigate to {url}
            b. Wait for page to fully load (5 seconds)
            c. Find and click on the navigation menu item with text: '{navigate_menu_item}'
            d. Wait for the new page to fully load (5 seconds)
            e. Extract MAIN CONTENT using CSS selector: body > main, body > article, body > div.content, body
            f. Fallback to body text if main containers not found
        """
    else:
        task_description = f"""
            a. Navigate to {url}
            b. Wait for page to fully load (5 seconds)
            c. Extract MAIN CONTENT using CSS selector: body > main, body > article, body > div.content, body
            d. Fallback to body text if main containers not found
        """

    try:
        agent = Agent(
            task=task_description.strip(),
            llm=llm,
            max_actions_per_step=6 if navigate_menu_item else 4,
        )

        history = await agent.run(max_steps=30)
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

    except Exception as e:
        return False, f"Error during agent-based extraction: {str(e)}"
    finally:
        from grpc import aio
        try:
            await aio.shutdown_channel()
        except AttributeError:
            print("Warning: Ignored AttributeError: module 'grpc.aio' has no attribute 'shutdown_channel'")



async def find_navigation_menu_items(url: str) -> list[str]:
    llm = ChatGoogleGenerativeAI(
        model='gemini-2.0-flash-exp',
        api_key=os.getenv('GEMINI_API_KEY')
    )

    try:
        agent = Agent(
            task=f"""a. Navigate to {url}
                 b. Wait for page to fully load (5 seconds)
                 c. Identify the main navigation menu on the page (look for <nav> elements or common navigation structures).
                 d. Extract the text content of each item within the navigation menu.
                 e. Return a list of text items from the navigation menu.""",
            llm=llm,
            max_actions_per_step=5,
        )

        history = await agent.run(max_steps=25)
        menu_items = history.extracted_content()

        if isinstance(menu_items, list):
            all_texts = [text.strip() for sublist in menu_items for text in sublist if isinstance(text, str)]
            unique_menu_items = list(dict.fromkeys(all_texts))
            return unique_menu_items
        elif isinstance(menu_items, str):
            unique_menu_items = [item.strip() for item in menu_items.strip().split('\n') if item.strip()]
            unique_menu_items = list(dict.fromkeys(unique_menu_items))
            return unique_menu_items
        else:
            return []

    except Exception as e:
        print(f"Error finding navigation menu items: {e}")
        return []
    finally:
        from grpc import aio
        try:
            await aio.shutdown_channel()
        except AttributeError:
            print("Warning: Ignored AttributeError: module 'grpc.aio' has no attribute 'shutdown_channel'")


async def process_page(page_url: str, navigate_menu_item: str = None) -> tuple[str, str]:
    success, content = await extract_content_with_agent(page_url, navigate_menu_item)
    if success:
        page_title = navigate_menu_item if navigate_menu_item else (urlparse(page_url).path.strip('/').replace('/', ' - ') or "Page")
        if not page_title or page_title == "Page":
            page_title = page_url
        return page_title, content
    else:
        page_title = navigate_menu_item if navigate_menu_item else (urlparse(page_url).path.strip('/') or "Error Page")
        return page_title, f"Error extracting content from {page_url} (Menu: {navigate_menu_item}): {content}"


async def main():
    import asyncio
    import platform

    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    st.markdown("<h1>🌐 Web Content Extractor</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p class='subheader'>Extract content from a web page with AI-powered cleaning</p>",
        unsafe_allow_html=True
    )

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        url = st.text_input(
            "Enter website URL:",
            placeholder="https://example.com",
            help="Paste the URL of the website you want to extract content from"
        )
        exploration_mode = st.radio(
            "Exploration Mode:",
            ["Single Page", "Navigation Menu Items"],
            index=0,
            help="Choose how to extract content from the website."
        )


        if st.button("🔍 Extract Content", type="primary", use_container_width=True):
            if url:
                if not url.startswith(('http://', 'https://')):
                    url = f'https://{url}'

                all_pages_info = {}
                progress_bar = st.progress(0)
                status_text = st.empty()


                if exploration_mode == "Navigation Menu Items":
                    with st.spinner("Finding navigation menu items..."):
                        menu_items = await find_navigation_menu_items(url)
                        if menu_items:
                            num_menu_items_to_process = len(menu_items) + 1
                            status_text.markdown(f"Processing 1 of {num_menu_items_to_process} pages...")

                            tasks = []
                            page_texts = ["Home"] + menu_items
                            tasks.append(process_page(url))

                            for menu_item in menu_items:
                                tasks.append(process_page(url, menu_item))

                            results = await asyncio.gather(*tasks)

                            for i, (page_title, content) in enumerate(results):
                                all_pages_info[page_texts[i]] = content
                                progress = int(((i + 1) / num_menu_items_to_process) * 100)
                                progress_bar.progress(progress)
                                if (i + 1) < num_menu_items_to_process:
                                    status_text.markdown(f"Processing page {i + 2} of {num_menu_items_to_process}...")
                                else:
                                    status_text.markdown("Processing complete!")
                        else:
                            st.warning("No navigation menu items found. Processing only the main page.")
                            num_menu_items_to_process = 1
                            tasks = [process_page(url)]
                            page_texts = ["Home"]
                            results = await asyncio.gather(*tasks)
                            page_title, content = results[0]
                            all_pages_info[page_texts[0]] = content
                            progress_bar.progress(100)
                            status_text.markdown("Processing complete!")


                elif exploration_mode == "Single Page":
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
            - Single Page or Navigation Menu Items
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