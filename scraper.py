import os
import re
import asyncio
from playwright.async_api import async_playwright

def parse_number(text: str) -> float:
    """從 '3,239 KM' 或 '1.89 KG' 字串中提取純數值"""
    cleaned = re.sub(r'[^\d.]', '', str(text))
    return float(cleaned) if cleaned else 0.0

async def query_icao_and_screenshot(origin_icao: str, dest_icao: str, weight_kg: float = 1.0, custom_route_key: str = None) -> dict:
    os.makedirs("screenshots", exist_ok=True)
    route_key = custom_route_key or f"{origin_icao}_{dest_icao}_{int(weight_kg)}KG"
    img_path = f"screenshots/{route_key}.png"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()

        try:
            await page.goto("https://icec.icao.int/", wait_until="networkidle", timeout=60000)
            
            # 切換至 Cargo / Shipment 模式
            cargo_tab = page.locator("text=/Cargo|Shipment/i").first
            if await cargo_tab.count() > 0:
                await cargo_tab.click()
                await page.wait_for_timeout(500)

            inputs = page.locator("input[type='text'], input[type='search'], input[type='number']")
            await inputs.nth(0).fill(origin_icao)
            await page.wait_for_timeout(800)
            await page.keyboard.press("ArrowDown")
            await page.keyboard.press("Enter")

            await inputs.nth(1).fill(dest_icao)
            await page.wait_for_timeout(800)
            await page.keyboard.press("ArrowDown")
            await page.keyboard.press("Enter")

            weight_input = page.locator("input[placeholder*='Weight' i], input[name*='weight' i]").first
            if await weight_input.count() > 0:
                await weight_input.fill(str(weight_kg))
            else:
                await inputs.nth(2).fill(str(weight_kg))

            calc_btn = page.locator("button:has-text('Calculate'), input[value*='Calculate']").first
            await calc_btn.click()

            await page.wait_for_selector("text=Total Trip Distance", timeout=20000)
            await page.wait_for_timeout(1500)

            body_text = await page.inner_text("body")
            dist_match = re.search(r"Total Trip Distance\s*([\d,]+\.?\d*)\s*KM", body_text, re.I)
            fuel_match = re.search(r"Total Aircraft Fuel Burn\s*([\d,]+\.?\d*)\s*KG", body_text, re.I)
            co2_match  = re.search(r"Total shipment CO[2₂]\s*([\d,]+\.?\d*)\s*KG", body_text, re.I)

            distance_km = parse_number(dist_match.group(1)) if dist_match else 0.0
            fuel_burn_kg = parse_number(fuel_match.group(1)) if fuel_match else 0.0
            co2_per_kg = parse_number(co2_match.group(1)) if co2_match else 0.0

            summary_box = page.locator("text=Summary").locator("..").locator("..")
            await summary_box.screenshot(path=img_path)

            return {
                "route_key": route_key,
                "origin_icao": origin_icao,
                "dest_icao": dest_icao,
                "base_weight_kg": weight_kg,
                "distance_km": distance_km,
                "fuel_burn_kg": fuel_burn_kg,
                "co2_per_kg": co2_per_kg,
                "screenshot_file": img_path,
                "status": "Completed" if distance_km > 0 else "Failed"
            }
        except Exception as e:
            print(f"Error querying {origin_icao} -> {dest_icao}: {e}")
            return {
                "route_key": route_key,
                "origin_icao": origin_icao,
                "dest_icao": dest_icao,
                "base_weight_kg": weight_kg,
                "distance_km": 0.0,
                "fuel_burn_kg": 0.0,
                "co2_per_kg": 0.0,
                "screenshot_file": img_path,
                "status": "Failed"
            }
        finally:
            await browser.close()
