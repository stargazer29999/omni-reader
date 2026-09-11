"""Smart OS text extraction from active selection, focused windows, and documents."""

import os
import platform
import re
import shutil
import subprocess
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional
import pyperclip


class ArticleContentExtractor(HTMLParser):
    """Extracts clean article text from HTML, stripping boilerplate and ads."""
    def __init__(self):
        super().__init__()
        self.text_blocks = []
        self.ignore_tags = {
            'script', 'style', 'nav', 'header', 'footer', 'aside',
            'noscript', 'form', 'svg', 'button', 'iframe'
        }
        self.current_ignore = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.ignore_tags:
            self.current_ignore += 1

    def handle_endtag(self, tag):
        if tag.lower() in self.ignore_tags:
            self.current_ignore = max(0, self.current_ignore - 1)
        elif tag.lower() in {'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'li', 'article', 'section'}:
            self.text_blocks.append('\n')

    def handle_data(self, data):
        if self.current_ignore == 0:
            cleaned = data.strip()
            if cleaned:
                self.text_blocks.append(cleaned + ' ')


def extract_clean_article_from_html(html: str) -> str:
    parser = ArticleContentExtractor()
    parser.feed(html)
    full = ''.join(parser.text_blocks)
    return re.sub(r'\n\s*\n+', '\n\n', full).strip()


def get_clipboard_text() -> str:
    """Reads current clipboard text safely."""
    try:
        text = pyperclip.paste()
        return text.strip() if text else ""
    except Exception:
        if platform.system() == "Darwin":
            try:
                res = subprocess.run(["pbpaste"], capture_output=True, text=True, check=True)
                return res.stdout.strip()
            except Exception:
                pass
    return ""


def get_frontmost_app_name() -> str:
    """Returns the name of the currently focused macOS application."""
    if platform.system() != "Darwin":
        return ""
    cmd = 'tell application "System Events" to get name of first application process whose frontmost is true'
    try:
        res = subprocess.run(["osascript", "-e", cmd], capture_output=True, text=True, timeout=1)
        return res.stdout.strip()
    except Exception:
        return ""


def extract_from_safari() -> Optional[str]:
    """Extracts text from active Safari tab."""
    script = '''
    tell application "Safari"
        if (count of windows) > 0 then
            set docText to (text of front document)
            if docText is not missing value and length of docText > 50 then
                return docText
            end if
            return URL of front document
        end if
    end tell
    '''
    try:
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=2)
        val = res.stdout.strip()
        if val.startswith("http://") or val.startswith("https://"):
            return fetch_and_clean_url(val)
        return val if len(val) > 50 else None
    except Exception:
        return None


def extract_from_chromium_browser(app_name: str) -> Optional[str]:
    """Extracts URL and article text from Chrome, Brave, Edge, or Arc."""
    script = f'''
    tell application "{app_name}"
        if (count of windows) > 0 then
            return URL of active tab of front window
        end if
    end tell
    '''
    try:
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=2)
        url = res.stdout.strip()
        if url.startswith("http://") or url.startswith("https://"):
            return fetch_and_clean_url(url)
    except Exception:
        pass
    return None


def extract_from_preview() -> Optional[str]:
    """Extracts text from open PDF document in Preview."""
    script = '''
    tell application "Preview"
        if (count of documents) > 0 then
            return path of front document
        end if
    end tell
    '''
    try:
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=2)
        doc_path = res.stdout.strip()
        if doc_path and os.path.exists(doc_path) and doc_path.lower().endswith(".pdf"):
            try:
                from pypdf import PdfReader
                reader = PdfReader(doc_path)
                pages_text = []
                # Extract up to first 25 pages to prevent unbounded memory
                for page in reader.pages[:25]:
                    t = page.extract_text()
                    if t:
                        pages_text.append(t)
                return "\n\n".join(pages_text)
            except Exception as e:
                print(f"[Extractor] PDF extraction error: {e}")
    except Exception:
        pass
    return None


def extract_from_textedit() -> Optional[str]:
    """Extracts text from front document in TextEdit."""
    script = '''
    tell application "TextEdit"
        if (count of documents) > 0 then
            return text of front document
        end if
    end tell
    '''
    try:
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=2)
        return res.stdout.strip() if res.stdout.strip() else None
    except Exception:
        return None


def fetch_and_clean_url(url: str) -> Optional[str]:
    """Fetches URL HTML with realistic headers and extracts clean text."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            text = extract_clean_article_from_html(html)
            return text if len(text) > 100 else None
    except Exception as e:
        print(f"[Extractor] URL fetch note: {e}")
        return None


def get_selected_text() -> str:
    """Grabs active text selection (or clipboard if selection unchanged)."""
    system = platform.system()

    if system == "Linux":
        if shutil.which("wl-paste"):
            try:
                res = subprocess.run(["wl-paste", "-p", "--no-newline"], capture_output=True, text=True, timeout=1)
                if res.returncode == 0 and res.stdout.strip():
                    return res.stdout.strip()
            except Exception:
                pass
        if shutil.which("xclip"):
            try:
                res = subprocess.run(["xclip", "-o", "-selection", "primary"], capture_output=True, text=True, timeout=1)
                if res.returncode == 0 and res.stdout.strip():
                    return res.stdout.strip()
            except Exception:
                pass
        return get_clipboard_text()

    elif system == "Darwin":
        old_clip = get_clipboard_text()
        try:
            from pynput import keyboard
            kb = keyboard.Controller()
            with kb.pressed(keyboard.Key.cmd):
                kb.tap('c')
            time.sleep(0.08)
            new_clip = get_clipboard_text()
            if new_clip and new_clip != old_clip:
                return new_clip
        except Exception:
            pass

        return ""

    return get_clipboard_text()


def get_auto_context_text() -> str:
    """
    Intelligent context extraction:
    1. If user highlighted text -> returns selected text.
    2. If no text was highlighted -> inspects active application:
       - Safari -> active page text or article
       - Chrome / Brave / Edge / Arc -> active article text
       - Preview -> active PDF document content
       - TextEdit -> active document text
    3. Fallback: current clipboard text.
    """
    # 1. First check if user explicitly selected text
    selected = get_selected_text()
    if selected and len(selected.strip()) > 3:
        return selected.strip()

    # 2. Inspect frontmost application on macOS
    if platform.system() == "Darwin":
        app_name = get_frontmost_app_name()
        
        # Avoid self-reading terminal or Hermes
        if app_name.lower() in {"terminal", "iterm2", "hermes"}:
            clip = get_clipboard_text()
            return clip

        if "safari" in app_name.lower():
            text = extract_from_safari()
            if text:
                return text

        if any(b in app_name.lower() for b in ["brave", "chrome", "edge", "arc"]):
            text = extract_from_chromium_browser(app_name)
            if text:
                return text

        if "preview" in app_name.lower() or "skim" in app_name.lower():
            text = extract_from_preview()
            if text:
                return text

        if "textedit" in app_name.lower():
            text = extract_from_textedit()
            if text:
                return text

    # 3. Fallback to clipboard
    return get_clipboard_text()
