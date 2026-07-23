"""
Company Name to Ticker Search Utility

企業名からティッカーシンボルを検索する機能
"""

import difflib

# 主要企業の名前→ティッカーマッピング
# 日本企業（東証プライム .T 形式）、米国企業（NYSE/NASDAQ）、欧州企業を網羅
COMPANY_NAME_TO_TICKER: dict[str, str] = {
    # ============================================================
    # 米国企業 - Big Tech / FAANG
    # ============================================================
    "apple": "AAPL",
    "microsoft": "MSFT",
    "alphabet": "GOOGL",
    "google": "GOOGL",
    "amazon": "AMZN",
    "meta": "META",
    "facebook": "META",
    "tesla": "TSLA",
    "nvidia": "NVDA",
    "netflix": "NFLX",
    "adobe": "ADBE",
    "intel": "INTC",
    "amd": "AMD",
    "advanced micro devices": "AMD",
    "qualcomm": "QCOM",
    "broadcom": "AVGO",
    "cisco": "CSCO",
    "oracle": "ORCL",
    "salesforce": "CRM",
    "ibm": "IBM",
    "applied materials": "AMAT",
    "lam research": "LRCX",
    "kla corporation": "KLAC",
    "micron": "MU",
    "micron technology": "MU",
    "texas instruments": "TXN",
    "analog devices": "ADI",
    "marvell": "MRVL",
    "marvell technology": "MRVL",
    "servicenow": "NOW",
    "workday": "WDAY",
    "snowflake": "SNOW",
    "palantir": "PLTR",
    "crowdstrike": "CRWD",
    "fortinet": "FTNT",
    "palo alto networks": "PANW",
    "datadog": "DDOG",
    "twilio": "TWLO",
    "zoom": "ZM",
    "zoom video": "ZM",
    "uber": "UBER",
    "lyft": "LYFT",
    "airbnb": "ABNB",
    "doordash": "DASH",
    "coinbase": "COIN",
    "intuit": "INTU",
    "autodesk": "ADSK",
    "synopsys": "SNPS",
    "cadence": "CDNS",
    "veeva": "VEEV",
    "paypal": "PYPL",
    "block": "SQ",
    "square": "SQ",
    "stripe": "STRIPE",
    "akamai": "AKAM",
    "cloudflare": "NET",
    "splunk": "SPLK",
    "mongodb": "MDB",
    "elastic": "ESTC",
    "roper technologies": "ROP",
    "dell": "DELL",
    "dell technologies": "DELL",
    "hp": "HPQ",
    "hewlett packard": "HPQ",
    "hpe": "HPE",
    "hewlett packard enterprise": "HPE",
    "western digital": "WDC",
    "seagate": "STX",
    "corning": "GLW",
    # ============================================================
    # 米国企業 - 金融
    # ============================================================
    "jpmorgan": "JPM",
    "jp morgan": "JPM",
    "bank of america": "BAC",
    "wells fargo": "WFC",
    "citigroup": "C",
    "goldman sachs": "GS",
    "morgan stanley": "MS",
    "visa": "V",
    "mastercard": "MA",
    "american express": "AXP",
    "blackrock": "BLK",
    "charles schwab": "SCHW",
    "fidelity": "FNF",
    "t rowe price": "TROW",
    "franklin templeton": "BEN",
    "intercontinental exchange": "ICE",
    "cboe": "CBOE",
    "nasdaq": "NDAQ",
    "s&p global": "SPGI",
    "moody's": "MCO",
    "msci": "MSCI",
    "vanguard": "VGT",
    "blackstone": "BX",
    "kkr": "KKR",
    "apollo": "APO",
    "carlyle": "CG",
    "berkshire hathaway": "BRK-B",
    "berkshire": "BRK-B",
    "progressive": "PGR",
    "allstate": "ALL",
    "travelers": "TRV",
    "aig": "AIG",
    "metlife": "MET",
    "prudential": "PRU",
    "lincoln national": "LNC",
    "unum": "UNM",
    "aflac": "AFL",
    "hartford": "HIG",
    "chubb": "CB",
    "marsh mclennan": "MMC",
    # ============================================================
    # 米国企業 - ヘルスケア・医薬品
    # ============================================================
    "johnson johnson": "JNJ",
    "j&j": "JNJ",
    "pfizer": "PFE",
    "unitedhealth": "UNH",
    "unitedhealth group": "UNH",
    "merck": "MRK",
    "abbvie": "ABBV",
    "eli lilly": "LLY",
    "lilly": "LLY",
    "bristol myers": "BMY",
    "bristol myers squibb": "BMY",
    "abbott": "ABT",
    "abbott laboratories": "ABT",
    "thermo fisher": "TMO",
    "danaher": "DHR",
    "medtronic": "MDT",
    "stryker": "SYK",
    "boston scientific": "BSX",
    "becton dickinson": "BDX",
    "baxter": "BAX",
    "zimmer biomet": "ZBH",
    "edwards lifesciences": "EW",
    "iqvia": "IQV",
    "labcorp": "LH",
    "quest diagnostics": "DGX",
    "humana": "HUM",
    "cigna": "CI",
    "elevance health": "ELV",
    "centene": "CNC",
    "molina healthcare": "MOH",
    "cvs": "CVS",
    "cvs health": "CVS",
    "walgreens": "WBA",
    "mckesson": "MCK",
    "amerisourcebergen": "ABC",
    "cardinal health": "CAH",
    "gilead": "GILD",
    "gilead sciences": "GILD",
    "biogen": "BIIB",
    "regeneron": "REGN",
    "vertex": "VRTX",
    "vertex pharmaceuticals": "VRTX",
    "moderna": "MRNA",
    "biontech": "BNTX",
    "illumina": "ILMN",
    "agilent": "A",
    "waters": "WAT",
    # ============================================================
    # 米国企業 - 消費財・小売
    # ============================================================
    "walmart": "WMT",
    "coca cola": "KO",
    "pepsi": "PEP",
    "pepsico": "PEP",
    "procter gamble": "PG",
    "p&g": "PG",
    "nike": "NKE",
    "mcdonald": "MCD",
    "mcdonalds": "MCD",
    "starbucks": "SBUX",
    "home depot": "HD",
    "target": "TGT",
    "costco": "COST",
    "tjx": "TJX",
    "ross stores": "ROST",
    "dollar general": "DG",
    "dollar tree": "DLTR",
    "best buy": "BBY",
    "gap": "GPS",
    "lululemon": "LULU",
    "ralph lauren": "RL",
    "tapestry": "TPR",
    "hasbro": "HAS",
    "mattel": "MAT",
    "colgate": "CL",
    "colgate palmolive": "CL",
    "kimberly clark": "KMB",
    "clorox": "CLX",
    "church dwight": "CHD",
    "henkel": "HENKY",
    "unilever": "UL",
    "reckitt": "RBGLY",
    "mondelez": "MDLZ",
    "kraft heinz": "KHC",
    "general mills": "GIS",
    "kellogg": "K",
    "campbell soup": "CPB",
    "conagra": "CAG",
    "tyson foods": "TSN",
    "hormel": "HRL",
    "sysco": "SYY",
    "yum brands": "YUM",
    "restaurant brands": "QSR",
    "chipotle": "CMG",
    "darden": "DRI",
    "dominos": "DPZ",
    "marriott": "MAR",
    "hilton": "HLT",
    "hyatt": "H",
    "wyndham": "WH",
    "booking holdings": "BKNG",
    "expedia": "EXPE",
    # ============================================================
    # 米国企業 - エネルギー
    # ============================================================
    "exxon": "XOM",
    "exxonmobil": "XOM",
    "chevron": "CVX",
    "conocophillips": "COP",
    "schlumberger": "SLB",
    "slb": "SLB",
    "halliburton": "HAL",
    "baker hughes": "BKR",
    "pioneer natural": "PXD",
    "devon energy": "DVN",
    "marathon petroleum": "MPC",
    "valero": "VLO",
    "phillips 66": "PSX",
    "williams companies": "WMB",
    "kinder morgan": "KMI",
    "enphase": "ENPH",
    "first solar": "FSLR",
    "solaredge": "SEDG",
    "nextera energy": "NEE",
    "duke energy": "DUK",
    "southern company": "SO",
    "dominion": "D",
    "exelon": "EXC",
    "american electric power": "AEP",
    "xcel energy": "XEL",
    # ============================================================
    # 米国企業 - 産業・素材
    # ============================================================
    "boeing": "BA",
    "general electric": "GE",
    "ge": "GE",
    "caterpillar": "CAT",
    "honeywell": "HON",
    "3m": "MMM",
    "ford": "F",
    "general motors": "GM",
    "lockheed martin": "LMT",
    "raytheon": "RTX",
    "northrop grumman": "NOC",
    "l3harris": "LHX",
    "general dynamics": "GD",
    "deere": "DE",
    "john deere": "DE",
    "parker hannifin": "PH",
    "emerson electric": "EMR",
    "eaton": "ETN",
    "illinois tool works": "ITW",
    "itw": "ITW",
    "dover": "DOV",
    "roper": "ROP",
    "ametek": "AME",
    "xylem": "XYL",
    "fortive": "FTV",
    "waste management": "WM",
    "republic services": "RSG",
    "cintas": "CTAS",
    "copart": "CPRT",
    "fastenal": "FAST",
    "w w grainger": "GWW",
    "grainger": "GWW",
    "linear": "LIN",
    "linde": "LIN",
    "air products": "APD",
    "ecolab": "ECL",
    "sherwin williams": "SHW",
    "ppg": "PPG",
    "nucor": "NUE",
    "steel dynamics": "STLD",
    "freeport mcmoran": "FCX",
    "alcoa": "AA",
    "mosaic": "MOS",
    "cf industries": "CF",
    "corteva": "CTVA",
    "dupont": "DD",
    "dow": "DOW",
    "lyondellbasell": "LYB",
    "celanese": "CE",
    "eastman chemical": "EMN",
    "albemarle": "ALB",
    # ============================================================
    # 米国企業 - 通信・メディア
    # ============================================================
    "att": "T",
    "at&t": "T",
    "verizon": "VZ",
    "t-mobile": "TMUS",
    "tmobile": "TMUS",
    "comcast": "CMCSA",
    "charter": "CHTR",
    "disney": "DIS",
    "walt disney": "DIS",
    "fox": "FOXA",
    "paramount": "PARA",
    "warner bros": "WBD",
    "discovery": "WBD",
    "spotify": "SPOT",
    "iheartmedia": "IHRT",
    # ============================================================
    # 米国企業 - 不動産REIT
    # ============================================================
    "american tower": "AMT",
    "prologis": "PLD",
    "crown castle": "CCI",
    "equinix": "EQIX",
    "simon property": "SPG",
    "public storage": "PSA",
    "welltower": "WELL",
    "ventas": "VTR",
    "realty income": "O",
    "digital realty": "DLR",
    "iron mountain": "IRM",
    "weyerhaeuser": "WY",
    # ============================================================
    # ETF / インデックスファンド
    # ============================================================
    "spy": "SPY",
    "qqq": "QQQ",
    "vti": "VTI",
    "voo": "VOO",
    "dia": "DIA",
    "iwm": "IWM",
    "ief": "IEF",
    "tlt": "TLT",
    "gld": "GLD",
    "slv": "SLV",
    "uso": "USO",
    "xlk": "XLK",
    "xlv": "XLV",
    "xlf": "XLF",
    "xle": "XLE",
    "xli": "XLI",
    "xlp": "XLP",
    "xly": "XLY",
    "xlre": "XLRE",
    "arkk": "ARKK",
    "soxx": "SOXX",
    # ============================================================
    # 日本企業 - 自動車・輸送機器
    # ============================================================
    "トヨタ": "7203.T",
    "トヨタ自動車": "7203.T",
    "toyota": "7203.T",
    "ホンダ": "7267.T",
    "本田技研工業": "7267.T",
    "honda": "7267.T",
    "日産": "7201.T",
    "日産自動車": "7201.T",
    "nissan": "7201.T",
    "スズキ": "7269.T",
    "suzuki": "7269.T",
    "マツダ": "7261.T",
    "mazda": "7261.T",
    "subaru": "7270.T",
    "スバル": "7270.T",
    "三菱自動車": "7211.T",
    "mitsubishi motors": "7211.T",
    "いすゞ": "7202.T",
    "isuzu": "7202.T",
    "日野自動車": "7205.T",
    "hino": "7205.T",
    "豊田自動織機": "6201.T",
    "toyota industries": "6201.T",
    "アイシン": "7259.T",
    "aisin": "7259.T",
    "デンソー": "6902.T",
    "denso": "6902.T",
    "豊田紡織": "3116.T",
    "toyota boshoku": "3116.T",
    "ジェイテクト": "6473.T",
    "jtekt": "6473.T",
    # ============================================================
    # 日本企業 - 電機・電子部品
    # ============================================================
    "ソニー": "6758.T",
    "ソニーグループ": "6758.T",
    "sony": "6758.T",
    "パナソニック": "6752.T",
    "panasonic": "6752.T",
    "日立": "6501.T",
    "日立製作所": "6501.T",
    "hitachi": "6501.T",
    "三菱電機": "6503.T",
    "mitsubishi electric": "6503.T",
    "富士通": "6702.T",
    "fujitsu": "6702.T",
    "nec": "6701.T",
    "日本電気": "6701.T",
    "シャープ": "6753.T",
    "sharp": "6753.T",
    "京セラ": "6971.T",
    "kyocera": "6971.T",
    "村田製作所": "6981.T",
    "murata": "6981.T",
    "tdk": "6762.T",
    "日本電産": "6594.T",
    "ニデック": "6594.T",
    "nidec": "6594.T",
    "ローム": "6963.T",
    "rohm": "6963.T",
    "東京エレクトロン": "8035.T",
    "tel": "8035.T",
    "tokyo electron": "8035.T",
    "アドバンテスト": "6857.T",
    "advantest": "6857.T",
    "レーザーテック": "6920.T",
    "lasertec": "6920.T",
    "キーエンス": "6861.T",
    "keyence": "6861.T",
    "ファナック": "6954.T",
    "fanuc": "6954.T",
    "安川電機": "6506.T",
    "yaskawa": "6506.T",
    "オムロン": "6645.T",
    "omron": "6645.T",
    "任天堂": "7974.T",
    "nintendo": "7974.T",
    "信越化学": "4063.T",
    "shin etsu": "4063.T",
    "shin-etsu chemical": "4063.T",
    "住友電工": "5802.T",
    "sumitomo electric": "5802.T",
    "古河電工": "5801.T",
    "furukawa electric": "5801.T",
    "アルプスアルパイン": "6770.T",
    "alps alpine": "6770.T",
    "日本精工": "6471.T",
    "nsk": "6471.T",
    # ============================================================
    # 日本企業 - 鉄鋼・金属・素材
    # ============================================================
    "日本製鉄": "5401.T",
    "nippon steel": "5401.T",
    "jfeスチール": "5411.T",
    "jfe": "5411.T",
    "jfe holdings": "5411.T",
    "神戸製鋼": "5406.T",
    "kobe steel": "5406.T",
    "住友金属鉱山": "5713.T",
    "sumitomo metal mining": "5713.T",
    "三菱マテリアル": "5711.T",
    "mitsubishi materials": "5711.T",
    "東邦亜鉛": "5707.T",
    "toho zinc": "5707.T",
    "大阪チタニウム": "5726.T",
    "osaka titanium": "5726.T",
    # ============================================================
    # 日本企業 - 化学
    # ============================================================
    "三菱ケミカル": "4188.T",
    "mitsubishi chemical": "4188.T",
    "住友化学": "4005.T",
    "sumitomo chemical": "4005.T",
    "旭化成": "3407.T",
    "asahi kasei": "3407.T",
    "東レ": "3402.T",
    "toray": "3402.T",
    "帝人": "3401.T",
    "teijin": "3401.T",
    "クレハ": "4023.T",
    "kureha": "4023.T",
    "日本触媒": "4114.T",
    "nippon shokubai": "4114.T",
    "カネカ": "4118.T",
    "kaneka": "4118.T",
    "積水化学": "4204.T",
    "sekisui chemical": "4204.T",
    "花王": "4452.T",
    "kao": "4452.T",
    "ライオン": "4912.T",
    "lion": "4912.T",
    # ============================================================
    # 日本企業 - 食品・飲料
    # ============================================================
    "アサヒ": "2502.T",
    "アサヒグループ": "2502.T",
    "asahi": "2502.T",
    "キリン": "2503.T",
    "キリンhd": "2503.T",
    "kirin": "2503.T",
    "サントリー食品": "2587.T",
    "suntory": "2587.T",
    "味の素": "2802.T",
    "ajinomoto": "2802.T",
    "日清食品": "2897.T",
    "日清食品hd": "2897.T",
    "nissin": "2897.T",
    "明治hd": "2269.T",
    "meiji": "2269.T",
    "森永製菓": "2201.T",
    "morinaga": "2201.T",
    "カルビー": "2229.T",
    "calbee": "2229.T",
    "ニッスイ": "1332.T",
    "日本水産": "1332.T",
    "nissui": "1332.T",
    "マルハニチロ": "1334.T",
    "maruha nichiro": "1334.T",
    "山崎製パン": "2212.T",
    "yamazaki baking": "2212.T",
    "雪印メグミルク": "2270.T",
    "megmilk snow brand": "2270.T",
    # ============================================================
    # 日本企業 - 小売・流通
    # ============================================================
    "イオン": "8267.T",
    "aeon": "8267.T",
    "セブン＆アイ": "3382.T",
    "セブンイレブン": "3382.T",
    "seven & i": "3382.T",
    "ファーストリテイリング": "9983.T",
    "fast retailing": "9983.T",
    "uniqlo": "9983.T",
    "良品計画": "7453.T",
    "ムジルシ": "7453.T",
    "muji": "7453.T",
    "ニトリ": "9843.T",
    "ニトリhd": "9843.T",
    "nitori": "9843.T",
    "エービーシーマート": "2670.T",
    "abc mart": "2670.T",
    "パン・パシフィック": "7532.T",
    "pan pacific": "7532.T",
    "ドンキホーテ": "7532.T",
    "イトーヨーカ堂": "3382.T",
    "高島屋": "8233.T",
    "takashimaya": "8233.T",
    "三越伊勢丹": "3099.T",
    "isetan mitsukoshi": "3099.T",
    "大丸松坂屋": "8244.T",
    "j front retailing": "8244.T",
    "ヤマダ電機": "9831.T",
    "yamada": "9831.T",
    "エディオン": "2730.T",
    "edion": "2730.T",
    # ============================================================
    # 日本企業 - 金融
    # ============================================================
    "三菱ufjfg": "8306.T",
    "三菱ufj": "8306.T",
    "mitsubishi ufj": "8306.T",
    "mufg": "8306.T",
    "三井住友fg": "8316.T",
    "三井住友": "8316.T",
    "smfg": "8316.T",
    "sumitomo mitsui": "8316.T",
    "みずほfg": "8411.T",
    "みずほ": "8411.T",
    "mizuho": "8411.T",
    "野村hd": "8604.T",
    "野村": "8604.T",
    "nomura": "8604.T",
    "大和証券g": "8601.T",
    "daiwa securities": "8601.T",
    "第一生命": "8750.T",
    "dai-ichi life": "8750.T",
    "東京海上hd": "8766.T",
    "tokio marine": "8766.T",
    "損保ジャパン": "8630.T",
    "sompo": "8630.T",
    "ms&adインシュアランス": "8725.T",
    "ms&ad": "8725.T",
    "ゆうちょ銀行": "7182.T",
    "japan post bank": "7182.T",
    "りそなhd": "8308.T",
    "resona": "8308.T",
    "オリックス": "8591.T",
    "orix": "8591.T",
    "日本取引所g": "8697.T",
    "jpx": "8697.T",
    "SBIホールディングス": "8473.T",
    "sbi": "8473.T",
    "マネックスg": "8698.T",
    "monex": "8698.T",
    # ============================================================
    # 日本企業 - 通信・IT
    # ============================================================
    "ntt": "9432.T",
    "日本電信電話": "9432.T",
    "nippon telegraph": "9432.T",
    "kddi": "9433.T",
    "au": "9433.T",
    "ソフトバンク": "9434.T",
    "softbank corp": "9434.T",
    "ソフトバンクg": "9984.T",
    "softbank group": "9984.T",
    "softbank": "9984.T",
    "楽天": "4755.T",
    "rakuten": "4755.T",
    "nttデータ": "9613.T",
    "ntt data": "9613.T",
    "nttドコモ": "9432.T",
    "docomo": "9432.T",
    "サイバーエージェント": "4751.T",
    "cyberagent": "4751.T",
    "ディーエヌエー": "2432.T",
    "dena": "2432.T",
    "グリー": "3632.T",
    "gree": "3632.T",
    "スクウェア・エニックス": "9684.T",
    "square enix": "9684.T",
    "カプコン": "9697.T",
    "capcom": "9697.T",
    "コナミ": "9766.T",
    "konami": "9766.T",
    "セガサミー": "6460.T",
    "sega sammy": "6460.T",
    "バンダイナムコ": "7832.T",
    "bandai namco": "7832.T",
    "日立製作所 it": "6501.T",
    "tis": "3626.T",
    "伊藤忠テクノソリューションズ": "4657.T",
    "ctc": "4657.T",
    "野村総合研究所": "4307.T",
    "nri": "4307.T",
    "nomura research": "4307.T",
    "オービック": "4684.T",
    "obic": "4684.T",
    "日本オラクル": "4716.T",
    "oracle japan": "4716.T",
    "インターネットイニシアティブ": "3774.T",
    "iij": "3774.T",
    "gmo": "9449.T",
    "z holdings": "4689.T",
    "line yahoo": "4689.T",
    # ============================================================
    # 日本企業 - 医薬品・ヘルスケア
    # ============================================================
    "武田薬品": "4502.T",
    "takeda": "4502.T",
    "アステラス製薬": "4503.T",
    "astellas": "4503.T",
    "第一三共": "4568.T",
    "daiichi sankyo": "4568.T",
    "大塚hd": "4578.T",
    "otsuka": "4578.T",
    "塩野義製薬": "4507.T",
    "shionogi": "4507.T",
    "エーザイ": "4523.T",
    "eisai": "4523.T",
    "中外製薬": "4519.T",
    "chugai": "4519.T",
    "協和キリン": "4151.T",
    "kyowa kirin": "4151.T",
    "小野薬品": "4528.T",
    "ono pharmaceutical": "4528.T",
    "持田製薬": "4527.T",
    "mochida": "4527.T",
    "参天製薬": "4536.T",
    "santen": "4536.T",
    "テルモ": "4543.T",
    "terumo": "4543.T",
    "オリンパス": "7733.T",
    "olympus": "7733.T",
    "シスメックス": "6869.T",
    "sysmex": "6869.T",
    # ============================================================
    # 日本企業 - 建設・不動産
    # ============================================================
    "大和ハウス": "1925.T",
    "daiwa house": "1925.T",
    "積水ハウス": "1928.T",
    "sekisui house": "1928.T",
    "住友不動産": "8830.T",
    "sumitomo realty": "8830.T",
    "三井不動産": "8801.T",
    "mitsui fudosan": "8801.T",
    "三菱地所": "8802.T",
    "mitsubishi estate": "8802.T",
    "東急不動産hd": "3289.T",
    "tokyu fudosan": "3289.T",
    "野村不動産hd": "3231.T",
    "nomura real estate": "3231.T",
    "大成建設": "1801.T",
    "taisei": "1801.T",
    "鹿島建設": "1812.T",
    "kajima": "1812.T",
    "清水建設": "1803.T",
    "shimizu": "1803.T",
    "大林組": "1802.T",
    "obayashi": "1802.T",
    "竹中工務店": "1821.T",
    "takenaka": "1821.T",
    # ============================================================
    # 日本企業 - 機械・産業
    # ============================================================
    "コマツ": "6301.T",
    "komatsu": "6301.T",
    "クボタ": "6326.T",
    "kubota": "6326.T",
    "ダイキン工業": "6367.T",
    "daikin": "6367.T",
    "smc": "6273.T",
    "smcコーポレーション": "6273.T",
    "三菱重工": "7011.T",
    "mitsubishi heavy": "7011.T",
    "川崎重工": "7012.T",
    "kawasaki heavy": "7012.T",
    "ダイフク": "6383.T",
    "daifuku": "6383.T",
    "日本精機": "7287.T",
    "nippon seiki": "7287.T",
    "アマダ": "6113.T",
    "amada": "6113.T",
    "マキタ": "6586.T",
    "makita": "6586.T",
    "椿本チエイン": "6371.T",
    "tsubakimoto chain": "6371.T",
    # ============================================================
    # 日本企業 - 物流・運輸
    # ============================================================
    "日本郵船": "9101.T",
    "nyk": "9101.T",
    "nippon yusen": "9101.T",
    "商船三井": "9104.T",
    "mol": "9104.T",
    "mitsui osk": "9104.T",
    "川崎汽船": "9107.T",
    "k line": "9107.T",
    "anaホールディングス": "9202.T",
    "ana": "9202.T",
    "jal": "9201.T",
    "日本航空": "9201.T",
    "japan airlines": "9201.T",
    "ヤマトhd": "9064.T",
    "yamato": "9064.T",
    "佐川急便": "9143.T",
    "sgホールディングス": "9143.T",
    "sg holdings": "9143.T",
    "日本通運": "9062.T",
    "nippon express": "9062.T",
    "近鉄グループhd": "9041.T",
    "kintetsu": "9041.T",
    "東日本旅客鉄道": "9020.T",
    "jr東日本": "9020.T",
    "jreast": "9020.T",
    "東海旅客鉄道": "9022.T",
    "jr東海": "9022.T",
    "jr central": "9022.T",
    "西日本旅客鉄道": "9021.T",
    "jr西日本": "9021.T",
    "東急": "9005.T",
    "tokyu": "9005.T",
    "東武鉄道": "9001.T",
    "tobu": "9001.T",
    # ============================================================
    # 日本企業 - 商社
    # ============================================================
    "三菱商事": "8058.T",
    "mitsubishi corp": "8058.T",
    "三井物産": "8031.T",
    "mitsui": "8031.T",
    "伊藤忠商事": "8001.T",
    "itochu": "8001.T",
    "丸紅": "8002.T",
    "marubeni": "8002.T",
    "住友商事": "8053.T",
    "sumitomo corp": "8053.T",
    "豊田通商": "8015.T",
    "toyota tsusho": "8015.T",
    "双日": "2768.T",
    "sojitz": "2768.T",
    # ============================================================
    # 日本企業 - 自動車部品（サプライヤー）
    # ============================================================
    "パイオラックス": "5988.T",
    "piolax": "5988.T",
    "ユニプレス": "5949.T",
    "unipres": "5949.T",
    "日本発条": "5991.T",
    "nhk spring": "5991.T",
    "武蔵精密": "7220.T",
    "musashi": "7220.T",
    "伯東": "7433.T",
    "hakuto": "7433.T",
    "マクニカ": "3132.T",
    "マクニカホールディングス": "3132.T",
    "macnica": "3132.T",
    "macnica holdings": "3132.T",
    "加賀電子": "8154.T",
    "kaga electronics": "8154.T",
    "新光商事": "8141.T",
    "shinko shoji": "8141.T",
    "三信電気": "8150.T",
    "sanshin electronics": "8150.T",
    "イノテック": "9880.T",
    "innotech": "9880.T",
    "東海理化": "6995.T",
    "tokai rika": "6995.T",
    "タチエス": "7239.T",
    "tachi-s": "7239.T",
    "ダイハツ工業": "7262.T",
    "daihatsu": "7262.T",
    "プレス工業": "7246.T",
    "press kogyo": "7246.T",
    "ショーワ": "7274.T",
    "showa": "7274.T",
    "エクセディ": "7278.T",
    "exedy": "7278.T",
    "豊田合成": "7282.T",
    "toyoda gosei": "7282.T",
    "愛三工業": "7283.T",
    "aisan industry": "7283.T",
    "ニフコ": "7988.T",
    "nifco": "7988.T",
    "テイ・エス テック": "7313.T",
    "ts tech": "7313.T",
    "カルソニックカンセイ": "7248.T",
    "calsonic kansei": "7248.T",
    "日立アステモ": "6902.T",
    # ============================================================
    # 欧州企業
    # ============================================================
    "volkswagen": "VOW.DE",
    "vw": "VOW.DE",
    "bmw": "BMW.DE",
    "daimler": "MBG.DE",
    "mercedes": "MBG.DE",
    "mercedes benz": "MBG.DE",
    "siemens": "SIE.DE",
    "sap": "SAP.DE",
    "basf": "BAS.DE",
    "bayer": "BAYN.DE",
    "adidas": "ADS.DE",
    "continental": "CON.DE",
    "infineon": "IFX.DE",
    "shell": "SHEL",
    "bp": "BP",
    "astrazeneca": "AZN",
    "gsaxosmithkline": "GSK",
    "gsk": "GSK",
    "unilever uk": "ULVR.L",
    "hsbc": "HSBC",
    "barclays": "BCS",
    "lloyds": "LYG",
    "nestle": "NESN.SW",
    "novartis": "NOVN.SW",
    "roche": "ROG.SW",
    "ubs": "UBS",
    "credit suisse": "CS",
    "lvmh": "MC.PA",
    "loreal": "OR.PA",
    "l'oreal": "OR.PA",
    "hermes": "RMS.PA",
    "kering": "KER.PA",
    "airbus": "AIR.PA",
    "totalenergies": "TTE.PA",
    "stellantis": "STLA",
    "asml": "ASML",
    "ericsson": "ERIC",
    "nokia": "NOK",
    "volvo": "VOLV-B.ST",
    "ab inbev": "ABI.BR",
    "anheuser busch": "BUD",
    "heineken": "HEIA.AS",
    "philips": "PHG",
    "akzonobel": "AKZA.AS",
    "ing": "ING",
    "abn amro": "ABN.AS",
    "ferrari": "RACE",
    "stellantis eu": "STLAM.MI",
    "eni": "ENI.MI",
    "enel": "ENEL.MI",
    "intesa sanpaolo": "ISP.MI",
    "unicredit": "UCG.MI",
    "inditex": "ITX.MC",
    "zara": "ITX.MC",
    "santander": "SAN.MC",
    "banco bbva": "BBVA",
    # ============================================================
    # アジア・その他
    # ============================================================
    "samsung": "005930.KS",
    "sk hynix": "000660.KS",
    "hyundai": "005380.KS",
    "kia": "000270.KS",
    "lg electronics": "066570.KS",
    "posco": "005490.KS",
    "taiwan semiconductor": "TSM",
    "tsmc": "TSM",
    "alibaba": "BABA",
    "tencent": "0700.HK",
    "baidu": "BIDU",
    "jd.com": "JD",
    "meituan": "3690.HK",
    "pinduoduo": "PDD",
    "bytedance": "BDNCE",
    "xiaomi": "1810.HK",
    "reliance industries": "RELIANCE.NS",
    "infosys": "INFY",
    "tata consultancy": "TCS.NS",
    "wipro": "WIT",
    "hdfc bank": "HDB",
    "icici bank": "IBN",
}


def search_ticker_by_name(company_name: str, threshold: float = 0.6) -> str | None:
    """
    企業名からティッカーシンボルを検索（曖昧検索対応）

    Args:
        company_name: 企業名（部分一致可）
        threshold: 類似度のしきい値（0.0-1.0）

    Returns:
        ティッカーシンボル、見つからない場合はNone
    """
    if not company_name or not isinstance(company_name, str):
        return None

    query = company_name.lower().strip()

    # 完全一致
    if query in COMPANY_NAME_TO_TICKER:
        return COMPANY_NAME_TO_TICKER[query]

    # 部分一致
    for name, ticker in COMPANY_NAME_TO_TICKER.items():
        if query in name or name in query:
            return ticker

    # 曖昧検索（類似度ベース）
    matches = difflib.get_close_matches(
        query, COMPANY_NAME_TO_TICKER.keys(), n=1, cutoff=threshold
    )
    if matches:
        return COMPANY_NAME_TO_TICKER[matches[0]]

    return None


def search_companies(query: str, max_results: int = 10) -> list[tuple[str, str]]:
    """
    企業名で検索して候補リストを返す

    Args:
        query: 検索クエリ
        max_results: 最大結果数

    Returns:
        [(企業名, ティッカー), ...] のリスト

    Example:
        >>> search_companies("toyota")
        [('toyota', '7203.T'), ('トヨタ', '7203.T')]
    """
    if not query:
        return []

    query_lower = query.lower().strip()
    results = []

    # 完全一致・部分一致
    for name, ticker in COMPANY_NAME_TO_TICKER.items():
        if query_lower in name or name in query_lower:
            results.append((name, ticker))

    # 重複削除（同じティッカーは1つだけ）
    seen_tickers = set()
    unique_results = []
    for name, ticker in results:
        if ticker not in seen_tickers:
            seen_tickers.add(ticker)
            unique_results.append((name, ticker))

    return unique_results[:max_results]


def get_ticker_from_input(user_input: str) -> tuple[str, str]:
    """
    ユーザー入力からティッカーシンボルを取得

    ティッカーシンボルか企業名かを自動判定

    Args:
        user_input: ユーザーの入力（ティッカーまたは企業名）

    Returns:
        (ティッカーシンボル, 判定方法) のタプル
        判定方法: "ticker" または "name_search"

    Example:
        >>> get_ticker_from_input("AAPL")
        ('AAPL', 'ticker')
        >>> get_ticker_from_input("Apple")
        ('AAPL', 'name_search')
        >>> get_ticker_from_input("トヨタ")
        ('7203.T', 'name_search')
    """
    if not user_input:
        return "", "invalid"

    user_input = user_input.strip()

    # 優先1: 企業名マッピングをチェック（大文字・小文字どちらでも）
    # これにより、PIOLAX（大文字）も piolax（小文字）として検索される
    ticker = search_ticker_by_name(user_input)
    if ticker:
        return ticker, "name_search"

    # 優先2: ティッカーシンボル形式の判定
    # - 大文字のみ（例: AAPL）
    # - 数字+.T（例: 7203.T）
    # - 大文字+.DE/.SWなど（例: BMW.DE）
    if (
        (user_input.isupper() and len(user_input) <= 6)
        or ("." in user_input and user_input.split(".")[0].isdigit())
        or ("." in user_input and user_input.split(".")[0].isupper())
    ):
        return user_input.upper(), "ticker"

    # 判定できない場合はそのまま返す（ティッカーとして扱う）
    return user_input.upper(), "ticker"


def add_custom_mapping(company_name: str, ticker: str):
    """
    カスタム企業名マッピングを追加

    Args:
        company_name: 企業名
        ticker: ティッカーシンボル
    """
    COMPANY_NAME_TO_TICKER[company_name.lower()] = ticker.upper()
