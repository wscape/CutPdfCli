class Cpc < Formula
  desc "Fast CLI tool to split PDF files using table of contents"
  homepage "https://github.com/wscape/CutPdfCli"
  version "0.1.1"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/wscape/CutPdfCli/releases/download/v#{version}/cpc-macos-arm64.tar.gz"
      sha256 "89ce0049723c590d6474133294716109008cb581a49e678d5f8774c59b931df4"
    else
      url "https://github.com/wscape/CutPdfCli/releases/download/v#{version}/cpc-macos-x86_64.tar.gz"
      sha256 "2be3011742195d43239f3efb90993f505c35e8373b13edf01a95bb8bd764eb9d"
    end
  end

  on_linux do
    if Hardware::CPU.intel?
      url "https://github.com/wscape/CutPdfCli/releases/download/v#{version}/cpc-linux-x86_64.tar.gz"
      sha256 "dc6aded96cb37f8d55e154276c8f5b620cf003c7cf3b8daa663caaa608489d67"
    end
  end

  def install
    bin.install "cpc"
  end

  test do
    assert_match "cpc", shell_output("#{bin}/cpc --help")
  end
end
