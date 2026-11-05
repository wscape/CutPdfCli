#!/usr/bin/env bash
# CutPdfCli 단일 실행 파일 빌드 스크립트
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# 가상환경 내 python 인터프리터로 PyInstaller 실행
if [ -f "$DIR/.venv/bin/python" ]; then
    PYI=("$DIR/.venv/bin/python" -m PyInstaller)
elif [ -f "$DIR/.venv/bin/pyinstaller" ]; then
    PYI=("$DIR/.venv/bin/pyinstaller")
else
    PYI=("pyinstaller")
fi

echo "🚀 CutPdfCli 실행 파일 빌드 시작..."
export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-$DIR/.cache/pyinstaller}"

"${PYI[@]}" --clean CutPdfCli.spec

echo "✅ 빌드 완료: $DIR/dist/CutPdfCli"

