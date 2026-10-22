"""Git保存用にデータを圧縮・32 MiB以下に分割する。旧形式も復元可能。"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import tempfile


CHUNK_BYTES = 32 * 1024 * 1024
FILES = {"battles.jsonl.gz": "identity", "names.json": "gzip", "brawlers.json": "gzip"}


def pack(data, chunk_bytes=CHUNK_BYTES):
    if not 0 < chunk_bytes <= CHUNK_BYTES:
        raise ValueError("Invalid chunk size")
    data = Path(data)
    manifest = {"version": 1, "files": {}}
    with tempfile.TemporaryDirectory(dir=data, prefix=".pack-") as temp:
        temp = Path(temp)
        archive = temp / "archive"
        archive.mkdir()
        for name, codec in FILES.items():
            source = data / name
            encoded = temp / name
            if codec == "gzip":
                with source.open("rb") as src, encoded.open("wb") as raw:
                    with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as dst:
                        shutil.copyfileobj(src, dst)
            else:
                encoded = source
            parts = []
            with encoded.open("rb") as src:
                while block := src.read(chunk_bytes):
                    part = f"{name}.{len(parts):05d}.part"
                    (archive / part).write_bytes(block)
                    parts.append({"name": part, "size": len(block), "sha256": hashlib.sha256(block).hexdigest()})
            manifest["files"][name] = {"codec": codec, "size": source.stat().st_size, "parts": parts}
        (archive / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        # Verify every compressed stream and checksum before replacing the saved archive.
        restored = temp / "verified"
        restored.mkdir()
        _restore(archive, restored)
        for name in FILES:
            with (data / name).open("rb") as original, (restored / name).open("rb") as copy:
                while block := original.read(CHUNK_BYTES):
                    if block != copy.read(len(block)):
                        raise ValueError(f"Round-trip mismatch: {name}")
                if copy.read(1):
                    raise ValueError(f"Round-trip size mismatch: {name}")
        target = data / "archive"
        if target.exists():
            shutil.rmtree(target)
        archive.rename(target)
    print(f"Packed {sum(len(f['parts']) for f in manifest['files'].values())} parts; each <= {chunk_bytes} bytes")


def _restore(archive, target):
    manifest = json.loads((archive / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != 1 or set(manifest.get("files", {})) != set(FILES):
        raise ValueError("Unsupported or incomplete data archive")
    for name, codec in FILES.items():
        entry = manifest["files"][name]
        if entry["codec"] != codec:
            raise ValueError(f"Unexpected encoding: {name}")
        encoded = target / (name + ".encoded")
        with encoded.open("wb") as dst:
            for i, part in enumerate(entry["parts"]):
                if part["name"] != f"{name}.{i:05d}.part":
                    raise ValueError(f"Invalid part name: {name}")
                path = archive / part["name"]
                if not 0 < part["size"] <= CHUNK_BYTES or path.stat().st_size != part["size"]:
                    raise ValueError(f"Invalid part size: {path.name}")
                block = path.read_bytes()
                if hashlib.sha256(block).hexdigest() != part["sha256"]:
                    raise ValueError(f"Checksum mismatch: {path.name}")
                dst.write(block)
        output = target / name
        if codec == "gzip":
            with gzip.open(encoded, "rb") as src, output.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            encoded.unlink()
        else:
            encoded.rename(output)
        if output.stat().st_size != entry["size"]:
            raise ValueError(f"Restored size mismatch: {name}")
        if name.endswith(".gz"):
            with gzip.open(output, "rb") as src:
                while src.read(CHUNK_BYTES):
                    pass


def restore(data):
    data = Path(data)
    archive = data / "archive"
    if not archive.exists():
        # First migration: keep the existing files unchanged.
        for name in FILES:
            if not (data / name).is_file():
                raise FileNotFoundError(f"Missing saved data: {name}")
        print("Using legacy data; it will be migrated on the next save")
        return
    with tempfile.TemporaryDirectory(dir=data, prefix=".restore-") as temp:
        temp = Path(temp)
        _restore(archive, temp)
        for name in FILES:
            (temp / name).replace(data / name)
    print("Restored and verified all data parts")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("pack", "restore"))
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).parent / "data")
    args = parser.parse_args()
    (pack if args.command == "pack" else restore)(args.data_dir)
