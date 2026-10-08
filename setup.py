"""Bundle the canonical host skill without maintaining a second source copy."""

from pathlib import Path
import shutil

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildPyWithSkill(build_py):
    """Make the skill available to installed wheels through package resources."""

    def run(self):
        super().run()
        source = Path(__file__).resolve().parent / "skills" / "no-mistakes"
        if not (source / "SKILL.md").is_file():
            raise FileNotFoundError("The canonical No Mistakes skill is missing")
        target = Path(self.build_lib) / "no_mistakes" / "_skill"
        if target.exists():
            shutil.rmtree(target)
        for path in sorted(source.rglob("*.md")):
            destination = target / path.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)


setup(cmdclass={"build_py": BuildPyWithSkill})
