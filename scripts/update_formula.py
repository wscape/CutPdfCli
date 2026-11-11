#!/usr/bin/env python3
import hashlib
import sys
from pathlib import Path


def get_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def main():
    if len(sys.argv) < 2:
        print("Usage: update_formula.py <tag_name>")
        sys.exit(1)

    tag = sys.argv[1]
    version = tag.lstrip("v")

    dist_dir = Path("dist_all")
    sha_macos_arm64 = get_sha256(dist_dir / "cpc-macos-arm64.tar.gz")
    sha_macos_x86_64 = get_sha256(dist_dir / "cpc-macos-x86_64.tar.gz")
    sha_linux_x86_64 = get_sha256(dist_dir / "cpc-linux-x86_64.tar.gz")

    formula_content = f'''class Cpc < Formula
  desc "Fast CLI tool to split PDF files using table of contents"
  homepage "https://github.com/wscape/CutPdfCli"
  version "{version}"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/wscape/CutPdfCli/releases/download/v#{{version}}/cpc-macos-arm64.tar.gz"
      sha256 "{sha_macos_arm64}"
    else
      url "https://github.com/wscape/CutPdfCli/releases/download/v#{{version}}/cpc-macos-x86_64.tar.gz"
      sha256 "{sha_macos_x86_64}"
    end
  end

  on_linux do
    if Hardware::CPU.intel?
      url "https://github.com/wscape/CutPdfCli/releases/download/v#{{version}}/cpc-linux-x86_64.tar.gz"
      sha256 "{sha_linux_x86_64}"
    end
  end

  def install
    bin.install "cpc"
  end

  test do
    assert_match "cpc", shell_output("#{{bin}}/cpc --help")
  end
end
'''

    formula_path = Path("Formula/cpc.rb")
    formula_path.parent.mkdir(parents=True, exist_ok=True)
    formula_path.write_text(formula_content, encoding="utf-8")
    print(f"Updated {formula_path} for version {version}")


if __name__ == "__main__":
    main()
