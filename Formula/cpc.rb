class Cpc < Formula
  desc "Fast CLI tool to split PDF files using table of contents"
  homepage "https://github.com/wscape/CutPdfCli"
  version "0.1.3"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/wscape/CutPdfCli/releases/download/v#{version}/cpc-macos-arm64.tar.gz"
      sha256 "8069e26996f591f5795ad93bf5f5bb91e3ed7b6f7c55cdc0644e2f973355ff5f"
    else
      url "https://github.com/wscape/CutPdfCli/releases/download/v#{version}/cpc-macos-x86_64.tar.gz"
      sha256 "a90c3b3ef1e02673de4b17ba5e27c7695129396372443fce84cb9e7476303a8d"
    end
  end

  on_linux do
    if Hardware::CPU.intel?
      url "https://github.com/wscape/CutPdfCli/releases/download/v#{version}/cpc-linux-x86_64.tar.gz"
      sha256 "4f408240166408740d9b27ea7d45406ba57a57de55ce465ee193294f6d1c90a9"
    end
  end

  def install
    bin.install "cpc"
  end

  test do
    assert_match "cpc", shell_output("#{bin}/cpc --help")
  end
end
