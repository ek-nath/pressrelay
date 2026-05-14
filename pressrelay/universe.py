import os
import csv
from typing import Set, List
from pathlib import Path
from pressrelay.logger import logger

# Hardcoded fallback list (from healthcare-alpha)
DEFAULT_TICKERS = [
    # Large Cap Leaders
    "LLY", "JNJ", "ABBV", "MRK", "UNH", "TMO", "GILD", "ISRG", "PFE", "ABT", 
    "SYK", "ELV", "CVS", "MDT", "CI", "REGN", "ZTS", "BSX", "BMY", "VRTX", 
    "HCA", "MCK", "COR", "EW", "IQV", "DXCM", "ALGN", "IDXX", "CNC", "BIIB", 
    "HUM", "MTD", "RMD", "WAT", "STE", "BIO", "PKI", "HOLX", "COO", "LH", 
    "DGX", "BAX", "TFX", "ZBH", "XRAY", "HSIC", "ALNY", "MRNA", "BDX", "TECH", 
    "INCY", "VTRS", "OGN", "CTLT", "WST", "PRGO", "CRL", "RGEN", "QGEN", 

    # Mid/Small Cap & High Volatility Tickers
    "FENC", "ATYR", "LTRN", "IMRN", "CRBU", "CRMD", "ARCT", "OPK", "CDXS", "VKTX",
    "EXAS", "NTRA", "GH", "BEAM", "EDIT", "CRSP", "BLUE", "SRPT", "PTCT", "FATE", 
    "NKTR", "IRON", "IOVA", "ARVN", "KYMR", "RVMD", "KNSA", "CMRX", "CUE", "TGTX", 
    "BPMC", "AKRO", "CYTK", "IMTX", "RARE", "DTIL", "VERV", "BNGO", "PACB", "NVCR", 
    "AXSM", "ZYME", "ADMA", "XENE", "HALO", "PCVX", "MOR", "RYTM", "FOLD", "MDGL", 
    "APLS", "SAVA", "ANVS", "ATHA", "LCI", "AMPH", "ENDP", "PBYI", "AERI", "COLL", 
    "HERT", "CPRX", "AMRN", "SCYX", "VYGR", "SLDB", "PRTA", "AGIO", "GBT", "KRTX", 
    "AXON", "PRLD", "CCCC", "MORF", "ARQT", "ENCP", "STOK", "DYN", "SWTX", "KRON", 
    "IMGN", "ALXO", "CERE", "IDYA", "PCVX", "TNYA", "VTYX", "GRTS", "IMNM", "SYRS", 
    "MTEM", "KDNY", "RPHM", "ALEC", "XBIT", "ANAB", "AVRO", "SGTX", "FGEN", "KOD", 
    "CLVS", "EPZM", "GLPG", "BBIO", "RYVU", "APLT", "ASMB", "ENTA", "RIGL", "GTHX",
    "RVNC", "OCUL", "EYPT", "KALA", "CNCE", "SPPI", "TCDA", "AQB", "EVLO", "KALV", 
    "ALBO", "AMBO", "APLS", "ARAV", "ARWR", "ASND", "ATRA", "AUTL", "BCRX", "BOLD", 
    "CGEN", "CNTG", "DTIL", "EIGR", "FREQ", "FULC", "GMDA", "GOSS", "HARP", "IBIO", 
    "IDRA", "IMAB", "IMVT", "INBX", "ISEE", "IVVD", "KALV", "KPTI", "KRYS", "LXRX", 
    "MBRX", "MEIP", "MGTA", "MREO", "NGM", "NMTR", "NUVB", "ORIC", "PASG", "PLRX", 
    "PMVP", "RAPT", "RUBY", "SANA", "SNDX", "SNSE", "SRAX", "STTK", "TMDX", "TRVI", 
    "VNDA", "VOR", "VSTM", "XNCR", "YMTX", "ZURA", "ALHC", "ASTH", "PHR", "DH", 
    "GDRX", "AMWL", "ELAN", "CURLF", "EXEL", "GERN", "PCRX", "GMAB", "NVO"
]

def get_ticker_universe(csv_path: Optional[Path] = None) -> Set[str]:
    """
    Returns the set of tickers allowed for trading.
    Prioritizes the results from the latest screener run if a path is provided.
    """
    if csv_path and csv_path.exists():
        try:
            with open(csv_path, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                tickers = {row['Ticker'].strip() for row in reader if 'Ticker' in row and row['Ticker']}
                if tickers:
                    logger.info(f"[UNIVERSE] Loaded {len(tickers)} tickers from {csv_path}")
                    return tickers
        except Exception as e:
            logger.error(f"[UNIVERSE] Error loading screener results from {csv_path}: {e}")

    # Fallback to default list
    logger.debug(f"[UNIVERSE] Using default list ({len(DEFAULT_TICKERS)} tickers).")
    return set(DEFAULT_TICKERS)
