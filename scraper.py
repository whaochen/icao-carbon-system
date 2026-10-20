import os
import asyncio
from playwright.async_api import async_playwright

async def query_icao_and_screenshot(origin_icao: str, dest_icao: str, weight_kg: float = 1.0, custom_route_key: str = None) -> dict:
    os.makedirs("screenshots", exist_ok=True)
    w_float = float(weight_kg)
    route_key = custom_route_key or f"{origin_icao}_{dest_icao}_{int(w_float)}KG"
    img_path = f"screenshots/{route_key}.png"

    distance_km, fuel_burn_kg, co2_per_kg = 0.0, 0.0, 0.0

    async with async_playwright() as p:
        # 啟動無頭瀏覽器
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()

        try:
            # 1. 前往 ICAO 官網
            await page.goto("https://icec.icao.int/", wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(2000)

            # 2. 點擊 Cargo / Shipment 分頁
            cargo_tab = page.locator("text=/Cargo|Shipment/i").first
            if await cargo_tab.count() > 0:
                await cargo_tab.click()
                await page.wait_for_timeout(1000)

            # 3. 填入起點與終點站代碼 (觸發官網自動完成選單)
            inputs = page.locator("input[type='text'], input[type='search'], input[type='number']")
            if await inputs.count() >= 2:
                # 填入起點
                await inputs.nth(0).fill(origin_icao)
                await page.wait_for_timeout(1500)
                await page.keyboard.press("ArrowDown")
                await page.keyboard.press("Enter")

                # 填入終點
                await inputs.nth(1).fill(dest_icao)
                await page.wait_for_timeout(1500)
                await page.keyboard.press("ArrowDown")
                await page.keyboard.press("Enter")

                # 填入重量
                weight_input = page.locator("input[placeholder*='Weight' i], input[name*='weight' i]").first
                if await weight_input.count() > 0:
                    await weight_input.fill(str(w_float))
                elif await inputs.count() >= 3:
                    await inputs.nth(2).fill(str(w_float))

                # 4. 點擊 Calculate 按鈕
                calc_btn = page.locator("button:has-text('Calculate'), input[value*='Calculate']").first
                await calc_btn.click()

                # 5. 等待 Summary 結果出現
                await page.wait_for_selector("text=Total Trip Distance", timeout=25000)
                await page.wait_for_timeout(2000) # 確保國旗與數字完全載入

                # 6. 解析畫面上的真實數據
                body_text = await page.inner_text("body")
                import re
                def parse_num(t):
                    cleaned = re.sub(r'[^\d.]', '', str(t))
                    return float(cleaned) if cleaned else 0.0

                dist_match = re.search(r"Total Trip Distance\s*([\d,]+\.?\d*)\s*KM", body_text, re.I)
                fuel_match = re.search(r"Total Aircraft Fuel Burn\s*([\d,]+\.?\d*)\s*KG", body_text, re.I)
                co2_match  = re.search(r"Total shipment CO[2₂]\s*([\d,]+\.?\d*)\s*KG", body_text, re.I)

                distance_km = parse_num(dist_match.group(1)) if dist_match else 0.0
                fuel_burn_kg = parse_num(fuel_match.group(1)) if fuel_match else 0.0
                co2_per_kg = parse_num(co2_match.group(1)) if co2_match else 0.0

                # 7. 對官網的 Summary 區塊進行高畫質截圖 (與您提供的原圖完全一致)
                summary_box = page.locator("text=Summary").locator("..").locator("..")
                await summary_box.screenshot(path=img_path)

        except Exception as e:
            print(f"ICAO live screenshot error for {origin_icao} -> {dest_icao}: {e}")

        await browser.close()

    return {
        "route_key": route_key,
        "origin_icao": origin_icao,
        "dest_icao": dest_icao,
        "base_weight_kg": w_float,
        "distance_km": float(distance_km),
        "fuel_burn_kg": float(fuel_burn_kg),
        "co2_per_kg": float(co2_per_kg),
        "screenshot_file": img_path,
        "status": "Completed" if distance_km > 0 else "Failed"
    }
