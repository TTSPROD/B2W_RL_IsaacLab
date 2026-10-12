"""Extract missing legacy Isaac dependencies locally; never install OS packages."""
import hashlib
import lzma
from pathlib import Path
import shutil
import subprocess
import urllib.request

from run_support import ROOT,write_json,sha256,utc_now


def main():
    directory=ROOT/".runtime/isaac-native-libs";packages=directory/"packages"
    packages.mkdir(parents=True,exist_ok=True)
    base="https://archive.ubuntu.com/ubuntu/"
    suite="noble-updates"
    release=packages/"InRelease"
    release.write_bytes(urllib.request.urlopen(base+f"dists/{suite}/InRelease",timeout=60).read())
    subprocess.run(["gpgv","--keyring","/usr/share/keyrings/ubuntu-archive-keyring.gpg",str(release)],check=True)
    index_path="main/binary-amd64/Packages.xz"
    digest=next(line.split()[0] for line in release.read_text().splitlines()
        if line.strip().endswith(" "+index_path) and len(line.split()[0])==64)
    content=urllib.request.urlopen(base+f"dists/{suite}/{index_path}",timeout=60).read()
    if hashlib.sha256(content).hexdigest()!=digest:raise ValueError("Signed package index SHA mismatch")
    (packages/"Packages.xz").write_bytes(content)
    selected={}
    for paragraph in lzma.decompress(content).decode().split("\n\n"):
        fields=dict(line.split(": ",1) for line in paragraph.splitlines() if line and not line[0].isspace() and ": " in line)
        if fields.get("Package") in {"libxml2","libicu74"}:selected[fields["Package"]]=fields
    if set(selected)!={"libxml2","libicu74"}:raise ValueError("Missing pinned legacy packages in signed index")
    records=[]
    for name,fields in selected.items():
        target=packages/Path(fields["Filename"]).name
        if not target.exists():target.write_bytes(urllib.request.urlopen(base+fields["Filename"],timeout=60).read())
        if sha256(target)!=fields["SHA256"]:raise ValueError("Deb SHA mismatch: "+name)
        subprocess.run(["dpkg-deb","-x",str(target),str(directory)],check=True)
        records.append({"package":name,"version":fields["Version"],"url":base+fields["Filename"],"sha256":fields["SHA256"]})
    # This small GLU package is fetched from this host's already signed APT catalog.
    subprocess.run(["apt-get","download","libglu1-mesa"],cwd=packages,check=True)
    glu=next(packages.glob("libglu1-mesa*.deb"))
    expected=subprocess.check_output(["apt-cache","show","libglu1-mesa"],text=True)
    digest=next(line.split(": ",1)[1] for line in expected.splitlines() if line.startswith("SHA256: "))
    if sha256(glu)!=digest:raise ValueError("GLU deb SHA mismatch")
    subprocess.run(["dpkg-deb","-x",str(glu),str(directory)],check=True)
    records.append({"package":"libglu1-mesa","sha256":digest,"source":"host signed APT catalog"})
    write_json(directory/"manifest.json",{"created_utc":utc_now(),"system_packages_modified":False,
        "signed_release_sha256":sha256(release),"packages":records,
        "library_sha256":{p.relative_to(directory).as_posix():sha256(p) for p in directory.rglob("*.so*") if p.is_file()}})


if __name__=="__main__":main()
