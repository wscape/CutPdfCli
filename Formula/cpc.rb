class Cpc < Formula
  desc "Fast CLI tool to split PDF files using table of contents"
  homepage "https://github.com/wscape/CutPdfCli"
  version "0.2.1"

  on_macos do
    if Hardware::CPU.arm?
      url "https://github.com/wscape/CutPdfCli/releases/download/v#{version}/cpc-macos-arm64.tar.gz"
      sha256 "e73fff9ab853972404e114a4576c0479070cc4d1c937fb03b4f974c0445694ec"
    else
      url "https://github.com/wscape/CutPdfCli/releases/download/v#{version}/cpc-macos-x86_64.tar.gz"
      sha256 "904f3c782b05f7144909ac12e360cc1e0f5325fa392294edd09f38f44c230cd4"
    end
  end

  on_linux do
    if Hardware::CPU.intel?
      url "https://github.com/wscape/CutPdfCli/releases/download/v#{version}/cpc-linux-x86_64.tar.gz"
      sha256 "4202ff10dbff06d8eabc2ff288fa36d624f0a9721328dd6a56926ac63ea8b0c2"
    end
  end

  def install
    bin.install "cpc"
  end

  test do
    assert_match "cpc", shell_output("#{bin}/cpc --help")
  end
end
