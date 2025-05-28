#!/usr/bin/env python3
"""
Installation script for PubMedRAG dependencies
"""

import subprocess
import sys
from pathlib import Path

# Required packages with versions
REQUIRED_PACKAGES = [
    "biopython>=1.79",
    "openai>=1.0.0", 
    "sentence-transformers>=2.2.0",
    "chromadb>=0.4.0",
    "colorama>=0.4.4",
    "python-dotenv>=1.0.0",
    "click>=8.0.0",
    "tqdm>=4.64.0",
    "pandas>=1.5.0",
    "numpy>=1.21.0"
]

def install_package(package):
    """Install a single package using pip."""
    try:
        print(f"Installing {package}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        print(f"✅ Successfully installed {package}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install {package}: {e}")
        return False

def check_package(package_name):
    """Check if a package is already installed."""
    try:
        __import__(package_name)
        return True
    except ImportError:
        return False

def main():
    """Main installation function."""
    print("🧬 PubMedRAG Installation Script")
    print("=" * 50)
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required")
        sys.exit(1)
    
    print(f"✅ Python {sys.version.split()[0]} detected")
    
    # Install packages
    failed_packages = []
    
    for package in REQUIRED_PACKAGES:
        package_name = package.split(">=")[0].split("==")[0]
        
        # Skip if already installed (optional check)
        # if check_package(package_name.replace("-", "_")):
        #     print(f"📦 {package_name} already installed")
        #     continue
        
        if not install_package(package):
            failed_packages.append(package)
    
    # Summary
    print("\n" + "=" * 50)
    if failed_packages:
        print(f"❌ Installation completed with {len(failed_packages)} failures:")
        for package in failed_packages:
            print(f"   - {package}")
        print("\nPlease install failed packages manually:")
        print(f"pip install {' '.join(failed_packages)}")
        sys.exit(1)
    else:
        print("✅ All packages installed successfully!")
        print("\nNext steps:")
        print("1. Create .env file: python -c 'from pubmedrag.utils import create_env_template; create_env_template()'")
        print("2. Edit .env with your configuration")
        print("3. Run: pubmedrag")

if __name__ == "__main__":
    main()