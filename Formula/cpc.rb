class Cpc < Formula
  desc "Fast CLI tool to split PDF files using table of contents"
  homepage "https://github.com/wscape/CutPdfCli"
  version "0.1.2"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/wscape/CutPdfCli/releases/download/v#{version}/cpc-macos-arm64.tar.gz"
      sha256 "41a1c273d892852adc35c9f41855c04fdad8aa6d9b75659e28b66d3f172360ec"
    else
      url "https://github.com/wscape/CutPdfCli/releases/download/v#{version}/cpc-macos-x86_64.tar.gz"
      sha256 "ab1796bb4936d02d1c644284322991c7c83b1064163fa59cfbb094c90877ac6a"
    end
  end

  on_linux do
    if Hardware::CPU.intel?
      url "https://github.com/wscape/CutPdfCli/releases/download/v#{version}/cpc-linux-x86_64.tar.gz"
      sha256 "625efc3ae39ab6394ccc114447914b6084164585f68a6c88ceb4ff26173acfdf"
    end
  end

  def install
    bin.install "cpc"
  end

  test do
    assert_match "cpc", shell_output("#{bin}/cpc --help")
  end
end
