import os
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

import secrets

DRIVER_PATH = 'chromedriver.exe'

options = Options()
# options.headless = True
# options.add_argument("--window-size=1920,1200")


def scrape_whales(start_today=True):
    driver = webdriver.Chrome(options=options, executable_path=DRIVER_PATH)
    wait5 = WebDriverWait(driver, 5)
    wait10 = WebDriverWait(driver, 10)
    driver.get(secrets.WHALES_WEBSITE + "/login")
    driver.maximize_window()
    driver.find_element_by_css_selector('input[type="text"]').send_keys(secrets.WHALES_USERNAME)
    driver.find_element_by_css_selector('input[type="password"]').send_keys(secrets.WHALES_PASSW0RD)
    driver.find_element_by_css_selector('button[type="submit"]').click()
    # wait10.until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'div.left-flex')))
    wait10.until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'div:nth-child(1) > header')))
    driver.get(secrets.WHALES_WEBSITE + "/alerts")

    today = datetime.now().date()
    two_months_out = today + timedelta(days=65)
    today_txt = today.strftime('%m/%d/%Y')
    two_months_out_txt = two_months_out.strftime('%m/%d/%Y')

    # wait5.until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'div.react-datepicker__input-container')))
    wait5.until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'div.infinite-scroll-component__outerdiv')))


    wait5.until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'ion-icon[name="options-outline"]')))
    driver.find_element_by_css_selector('ion-icon[name="options-outline"]').click()

    if start_today:
        start_exp = driver.find_elements_by_css_selector('div.react-datepicker__input-container')[-2].find_element_by_css_selector('input')
        while start_exp.get_attribute('value') != today_txt:
            start_exp.send_keys(Keys.CONTROL + "a")
            start_exp.send_keys(Keys.DELETE)
            start_exp.send_keys(today_txt)
            start_exp.send_keys(Keys.RETURN)

    end_exp = driver.find_elements_by_css_selector('div.react-datepicker__input-container')[-1].find_element_by_css_selector('input')
    while end_exp.get_attribute('value') != two_months_out_txt:
        end_exp.send_keys(Keys.CONTROL + "a")
        end_exp.send_keys(Keys.DELETE)
        end_exp.send_keys(two_months_out_txt)
        end_exp.send_keys(Keys.RETURN)

    wait5.until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'div.infinite-scroll-component')))
    div = driver.find_element_by_css_selector('div.infinite-scroll-component')
    while int(div.get_attribute('scrollTop')) < 200000:
        driver.execute_script("document.querySelector('div.infinite-scroll-component').scrollBy(0, 50000)")

    driver.maximize_window()
    table = driver.find_element_by_css_selector('table.alerts-table')
    df = pd.read_html(table.get_attribute('outerHTML'))[0]

    gain_loss_regex = r'\$(-?\d+\.\d+)(\s\((-?\d+\.\d+)%\))?'
    max_gain = df['Max Gain'].str.extract(gain_loss_regex).fillna(0)
    df['Max Gain Pct'] = max_gain[2].astype(float)
    df['Max Gain'] = max_gain[0].astype(float)

    max_loss = df['Max Loss'].str.extract(gain_loss_regex).fillna(0)
    df['Max Loss Pct'] = max_loss[2].astype(float)
    df['Max Loss'] = max_loss[0].astype(float)

    dt = pd.to_datetime(df['@'], format='%m/%d/%Y, %H:%M')
    df['Order Time'] = dt.dt.time
    df['Order Date'] = dt.dt.date

    df['PC'] = 'Put'
    df.loc[df['Option'].str.contains(' C'), 'PC'] = 'Call'

    df['Ticker'] = df['Option'].str.split(' ', expand=True)[0]
    df['Strike'] = df['Option'].str.split(' ', expand=True)[1].str.replace('$', '')

    df['Premium'] = df['Daily $ Vol'].str.replace(r'[\$,]', '').astype(float)
    # src['Premium'] = src['Premium'].apply(lambda x: '${:,.2f}'.format(x))

    del df['Daily $ Vol']
    del df['Tier']
    del df['@']
    del df['Actions']
    df['Vol/OI'] = df['Volume']/df['OI']

    # df['% OTM'] = df['Option']
    df.to_excel('raw_flow.xlsx', index=False)
    driver.quit()


if __name__ == '__main__':
    scrape_whales(start_today=True)
    src = pd.read_excel('raw_flow.xlsx', engine='openpyxl')

    # src['Order Date'].dt. = src['Order Time']
    df = src.reindex(columns=['Option', 'Expiry',
                              'OI', 'Volume', 'Vol/OI', 'IV', 'Premium',
                              'OG ask', 'Max Gain Pct', 'Max Loss Pct',
                              'Emojis', 'Ticker', 'PC', 'Strike', 'Order Date', 'Order Time']) \
        .sort_values(by=['Order Date', 'Order Time'], ascending=[True, True])
    df['Order Date'] = df['Order Date'].dt.date

    ask_side = df['Emojis'].str.contains("Ask Side")
    low_iv = df['IV'] < 150
    low_oi = df['Vol/OI'] > 3
    not_yet_profitable = df['Max Gain Pct'] < 60
    not_profitable_at_all = df['Max Gain Pct'] < 20
    profitable = df['Max Gain Pct'] >= 60
    very_profitable = df['Max Gain Pct'] >= 100
    very_very_profitable = df['Max Gain Pct'] >= 200
    bullish = df['PC'] == 'Call'
    bearish = df['PC'] == 'Put'
    all_plays = df[ask_side & low_iv & low_oi & not_yet_profitable]
    bull_plays = df[ask_side & low_iv & low_oi & not_yet_profitable & bearish]
    bear_plays = df[ask_side & low_iv & low_oi & not_yet_profitable & bearish]
    plays = df[ask_side & low_iv & low_oi & not_yet_profitable]

    expired = pd.to_datetime(df['Expiry'], format='%Y-%m-%d') < datetime.now()
    losers = df[expired & not_profitable_at_all]
    winners_qualified = df[ask_side & low_iv & low_oi & very_profitable]
    winners_all = df[very_profitable]
    big_winners_qualified = df[ask_side & low_iv & low_oi & very_very_profitable]
    big_winners_all = df[very_very_profitable]

    plays.to_excel('plays.xlsx', index=False)
    by_ticker = plays.sort_values(by=['Ticker', 'Order Date'], ascending=[True, True])
    by_exp = plays.sort_values(by=['Expiry', 'Ticker', 'PC', 'Strike'], ascending=[True, True, True, True])

    os.startfile('plays.xlsx')

