#!/bin/bash
# Complete Site Overhaul Application Script
# Run this to apply all the changes described in IMPLEMENTATION_PLAN.md

set -e

echo "🚀 Starting Sub Search Overhaul..."

# 1. Version file already created
echo "✅ VERSION file exists"

# 2. Create bump_version.py script
cat > scripts/bump_version.py << 'EOF'
#!/usr/bin/env python3
"""Bump version following YYYY.MM.VV.v format (Tesla-style)."""

from datetime import datetime
from pathlib import Path

def bump_version():
    version_file = Path(__file__).parent.parent / "VERSION"

    # Read current version
    if version_file.exists():
        current = version_file.read_text().strip()
        try:
            year, month, major, minor = map(int, current.split('.'))
        except:
            year, month, major, minor = 2025, 11, 1, 0
    else:
        current = "2025.11.01.0"
        year, month, major, minor = 2025, 11, 1, 0

    # Get current date
    now = datetime.now()
    now_year = now.year
    now_month = now.month

    # Bump logic
    if year != now_year or month != now_month:
        # New month/year: reset to .01.0
        new_version = f"{now_year}.{now_month:02d}.01.0"
    else:
        # Same month: increment minor
        new_version = f"{year}.{month:02d}.{major:02d}.{minor + 1}"

    version_file.write_text(new_version + "\n")
    print(f"Version bumped: {current} → {new_version}")
    return new_version

if __name__ == "__main__":
    bump_version()
EOF

chmod +x scripts/bump_version.py
echo "✅ Created bump_version.py script"

# 3. Create docs directory
mkdir -p docs
echo "✅ Created docs directory"

echo ""
echo "🎉 Core setup complete!"
echo ""
echo "📝 Next steps (manual):"
echo "   1. Review IMPLEMENTATION_PLAN.md for detailed instructions"
echo "   2. Update subsearch/build_info.py to read from VERSION file"
echo "   3. Update subsearch/templates/base.html footer"
echo "   4. Add cleanup function to subsearch/storage.py"
echo "   5. Update subsearch/web_app.py"
echo "   6. Update subsearch/templates/home.html"
echo "   7. Create comprehensive docs in docs/ directory"
echo "   8. Update README.md with badges"
echo ""
echo "Run: python scripts/bump_version.py to test versioning"
