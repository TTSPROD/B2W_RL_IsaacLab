"""Compatibility client; no HTTP server is required to submit work."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from process_client import submit
