"""Conserva avisos legales de las dependencias en la distribución."""
from importlib.metadata import distribution
from pathlib import Path
import shutil
import sys

root = Path(__file__).resolve().parents[1]
destination = root/'dist/TresVizo-Med/licencias'
destination.mkdir(parents=True, exist_ok=True)
for name in ('Pillow', 'reportlab', 'pypdfium2', 'PyInstaller', 'charset-normalizer'):
    package = distribution(name)
    target = destination/name
    target.mkdir(exist_ok=True)
    for item in package.files or []:
        if any(part.lower().startswith(('license', 'licence', 'copying', 'notice')) for part in item.parts):
            source = Path(package.locate_file(item))
            if source.is_file():
                relative = Path(*item.parts[-2:])
                output = target/relative
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, output)
    (target/'version.txt').write_text(f'{name} {package.version}\n', encoding='utf-8')
python_license = Path(sys.base_prefix)/'LICENSE.txt'
if python_license.exists():
    shutil.copyfile(python_license, destination/'Python-LICENSE.txt')
shutil.copyfile(root/'LICENSE', destination/'Proyecto-LICENSE.txt')
