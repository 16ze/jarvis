import os
import asyncio
import base64
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from google import genai
from google.genai import types

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY not set in .env")

SCREEN_WIDTH  = 1280
SCREEN_HEIGHT = 800

# gemini-2.5-flash: vision support, function calling
AGENT_MODEL = "gemini-2.5-flash"

SYSTEM_PROMPT = """You are a web browsing agent with full control over a real Chromium browser.
Your job is to complete the user's research task by navigating websites and extracting information.

Rules:
- ALWAYS use search_google (which uses Brave Search) to search — never navigate to google.com or bing.com directly as they block headless browsers.
- Use the page screenshot AND page_text to understand what is on screen.
- Click, type, scroll as needed to reach your goal.
- When you have gathered enough information to fully answer the task, call finish() with a clear summary.
- Be thorough: visit multiple sources if needed.
- Do NOT call finish() until you have real information to report.
- If a page blocks you or shows a CAPTCHA, use search_google with a different query or navigate to a different source.
"""

# ── Tool declarations (function calling, NOT Computer Use) ──────────────────

_tools = [
    {
        "name": "navigate",
        "description": "Navigate the browser to a URL.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url": {"type": "STRING", "description": "Full URL including https://"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "search_google",
        "description": "Search Google for a query and navigate to the results page.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Search query"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "click_at",
        "description": "Click at normalized coordinates (0-1000 scale).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "x": {"type": "INTEGER", "description": "Horizontal position, 0-1000"},
                "y": {"type": "INTEGER", "description": "Vertical position, 0-1000"}
            },
            "required": ["x", "y"]
        }
    },
    {
        "name": "type_text",
        "description": "Type text into the currently focused element.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "text":        {"type": "STRING",  "description": "Text to type"},
                "press_enter": {"type": "BOOLEAN", "description": "Press Enter after typing"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "scroll",
        "description": "Scroll the page up or down.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "direction": {"type": "STRING",  "description": "'up' or 'down'"},
                "amount":    {"type": "INTEGER", "description": "Pixels to scroll (default 600)"}
            },
            "required": ["direction"]
        }
    },
    {
        "name": "go_back",
        "description": "Navigate back to the previous page.",
        "parameters": {"type": "OBJECT", "properties": {}}
    },
    {
        "name": "get_page_text",
        "description": "Get the visible text content of the current page to read its content.",
        "parameters": {"type": "OBJECT", "properties": {}}
    },
    {
        "name": "finish",
        "description": "Call this when the task is complete. Provide a full summary of findings.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "result": {"type": "STRING", "description": "Complete answer / summary of findings"}
            },
            "required": ["result"]
        }
    }
]

_gemini_tools = [{"function_declarations": _tools}]


class WebAgent:
    def __init__(self):
        self.client = genai.Client(api_key=API_KEY)
        self.page   = None

    # ── Helpers ────────────────────────────────────────────────────────────

    def _px(self, norm: int, total: int) -> int:
        return int((norm / 1000) * total)

    async def _screenshot(self) -> tuple[bytes, str]:
        raw = await self.page.screenshot(type="png")
        return raw, base64.b64encode(raw).decode()

    async def _page_text(self) -> str:
        """Extract visible text from the page (truncated to 8000 chars)."""
        try:
            text = await self.page.evaluate("""() => {
                const el = document.body;
                return el ? el.innerText : '';
            }""")
            return (text or "")[:8000]
        except Exception:
            return ""

    # ── Action execution ───────────────────────────────────────────────────

    async def _execute(self, fn_name: str, args: dict) -> str:
        """Execute one browser action. Returns a status string."""
        try:
            if fn_name == "navigate":
                url = args["url"]
                if not url.startswith("http"):
                    url = "https://" + url
                await self.page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(2)
                return f"Navigated to {self.page.url}"

            elif fn_name == "search_google":
                q = args["query"]
                import urllib.parse
                # Use Brave Search — no CAPTCHA, works perfectly with headless browsers
                url = f"https://search.brave.com/search?q={urllib.parse.quote(q)}"
                await self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(1.5)
                return f"Searched for: {q}"

            elif fn_name == "click_at":
                x = self._px(args["x"], SCREEN_WIDTH)
                y = self._px(args["y"], SCREEN_HEIGHT)
                await self.page.mouse.click(x, y)
                await asyncio.sleep(1.5)
                return f"Clicked at ({x}, {y})"

            elif fn_name == "type_text":
                await self.page.keyboard.type(args["text"])
                if args.get("press_enter"):
                    await self.page.keyboard.press("Enter")
                    await asyncio.sleep(2)
                return f"Typed: {args['text'][:50]}"

            elif fn_name == "scroll":
                amount = args.get("amount", 600)
                dy = amount if args["direction"] == "down" else -amount
                await self.page.mouse.wheel(0, dy)
                await asyncio.sleep(0.8)
                return f"Scrolled {args['direction']} {amount}px"

            elif fn_name == "go_back":
                await self.page.go_back(wait_until="domcontentloaded", timeout=10000)
                await asyncio.sleep(1)
                return "Went back"

            elif fn_name == "get_page_text":
                text = await self._page_text()
                return text[:4000]  # returned as function result

            elif fn_name == "finish":
                return "__DONE__"

            else:
                return f"Unknown action: {fn_name}"

        except Exception as e:
            return f"Error in {fn_name}: {e}"

    # ── Main task loop ─────────────────────────────────────────────────────

    async def run_task(self, prompt: str, update_callback=None) -> str:
        print(f"[WEB AGENT] Task: {prompt}")
        final_result = "Task completed."

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            )
            ctx = await browser.new_context(
                viewport={"width": SCREEN_WIDTH, "height": SCREEN_HEIGHT},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            # Hide webdriver fingerprint
            await ctx.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            self.page = await ctx.new_page()
            await self.page.goto("about:blank")

            # Initial screenshot → frontend
            raw, b64 = await self._screenshot()
            if update_callback:
                await update_callback(b64, "Web Agent ready — starting task...")

            # Build first message: task + screenshot
            chat_history = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part(text=prompt),
                        types.Part.from_bytes(data=raw, mime_type="image/png"),
                    ]
                )
            ]

            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=_gemini_tools,
                temperature=0.1,
            )

            MAX_TURNS = 25

            for turn in range(MAX_TURNS):
                print(f"[WEB AGENT] Turn {turn + 1} | url={self.page.url}")

                # Retry loop for 429 rate limits
                response = None
                for attempt in range(3):
                    try:
                        response = await self.client.aio.models.generate_content(
                            model=AGENT_MODEL,
                            contents=chat_history,
                            config=config,
                        )
                        break
                    except Exception as e:
                        err_str = str(e)
                        if "429" in err_str and attempt < 2:
                            wait = 15 * (attempt + 1)
                            print(f"[WEB AGENT] Rate limit, retrying in {wait}s...")
                            if update_callback:
                                await update_callback(None, f"Rate limit — waiting {wait}s before retry...")
                            await asyncio.sleep(wait)
                        else:
                            print(f"[WEB AGENT] API error: {e}")
                            if update_callback:
                                await update_callback(None, f"Error: {e}")
                            await browser.close()
                            return final_result
                if response is None:
                    break

                if not response.candidates:
                    print("[WEB AGENT] Empty response.")
                    break

                model_content = response.candidates[0].content
                chat_history.append(model_content)

                # Extract text and function calls from response
                function_calls = []
                for part in model_content.parts:
                    if getattr(part, "text", None):
                        is_thought = getattr(part, "thought", False)
                        label = "Thought" if is_thought else "Text"
                        print(f"[WEB AGENT] {label}: {part.text[:200]}")
                    if getattr(part, "function_call", None):
                        function_calls.append(part.function_call)

                if not function_calls:
                    # Model responded with text only — done
                    # gemini-2.5 puts thinking first, actual answer last — take last text part
                    all_text = [p.text for p in model_content.parts if getattr(p, "text", None)]
                    final_result = all_text[-1] if all_text else final_result
                    raw, b64 = await self._screenshot()
                    if update_callback:
                        await update_callback(b64, f"Complete: {final_result[:100]}")
                    break

                # Execute each function call
                function_response_parts = []

                for fc in function_calls:
                    fn_name = fc.name
                    args    = dict(fc.args) if fc.args else {}
                    print(f"[WEB AGENT] → {fn_name}({args})")

                    if fn_name == "finish":
                        final_result = args.get("result", "Done.")
                        raw, b64 = await self._screenshot()
                        if update_callback:
                            await update_callback(b64, f"✓ {final_result[:120]}")
                        # Send function response then break outer loop
                        function_response_parts.append(
                            types.Part(
                                function_response=types.FunctionResponse(
                                    name=fn_name,
                                    id=getattr(fc, "id", None),
                                    response={"result": "done"},
                                )
                            )
                        )
                        chat_history.append(
                            types.Content(role="user", parts=function_response_parts)
                        )
                        await browser.close()
                        return final_result

                    # Execute the action
                    action_result = await self._execute(fn_name, args)

                    function_response_parts.append(
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=fn_name,
                                id=getattr(fc, "id", None),
                                response={"result": action_result},
                            )
                        )
                    )

                # After all actions: take screenshot, add to history
                raw, b64 = await self._screenshot()

                # Screenshot as top-level Part so model sees the updated page
                function_response_parts.append(
                    types.Part.from_bytes(data=raw, mime_type="image/png")
                )

                chat_history.append(
                    types.Content(role="user", parts=function_response_parts)
                )

                # Update frontend
                if update_callback:
                    actions_str = ", ".join(fc.name for fc in function_calls)
                    await update_callback(b64, f"→ {actions_str} | {self.page.url}")

            await browser.close()
            print("[WEB AGENT] Done.")
            return final_result


if __name__ == "__main__":
    async def _test():
        agent = WebAgent()

        async def cb(img, log):
            print(f"  [{log[:80]}] screenshot={'yes' if img else 'no'}")

        result = await agent.run_task(
            "Search Google for 'latest AI news 2025' and summarize the top 3 results.",
            update_callback=cb,
        )
        print("\nFinal result:", result)

    asyncio.run(_test())
