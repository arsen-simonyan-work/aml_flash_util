# Packaging and Release

This scaffold was generated for `Amlogic Flash Tool`.

Generated files:
- `AmlogicFlashTool.spec`
- `.github/workflows/release-packages.yml`
- `scripts/generate_icons.py`
- `scripts/validate_version.py`
- `version.py`
- `app_paths.py`
- `assets/icons/*`
- `build_linux.sh`
- `scripts/build_deb.py`

Release flow:
1. Update `VERSION`
2. Commit changes
3. Push a git tag matching `VERSION`
4. GitHub Actions will build release packages for the selected platforms

Example:
```bash
git tag 0.1.0
git push origin 0.1.0
```

Notes:
- Selected platforms: Linux
- Release artifacts: deb
- Your application entry script is set to `main.py`
- Your package name is `amlogic-flash-tool`
- Your bundle id is `com.home.amlogicflashtool`
- Your executable name is `AmlogicFlashTool`
