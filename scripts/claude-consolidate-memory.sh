#!/bin/bash
# Claude Code Memory Consolidation Script
# Run weekly (Monday) or when memory files > 20

set -e

MEMORY_DIR=~/.claude/projects/-opt-bms-intelligence/memory
ARCHIVE_DIR=~/.claude/memory-archive/$(date +%Y-%m)
TIMESTAMP=$(date +%Y%m%d)

echo "=== CLAUDE MEMORY CONSOLIDATION ==="
echo "Date: $(date)"
echo "Memory dir: $MEMORY_DIR"
echo "Archive dir: $ARCHIVE_DIR"
echo ""

# 1. Create archive directory
mkdir -p $ARCHIVE_DIR

# 2. Count current files
FILE_COUNT=$(ls $MEMORY_DIR/*.md 2>/dev/null | wc -l)
echo "Current memory files: $FILE_COUNT"

if [ $FILE_COUNT -le 20 ]; then
    echo "✅ File count within limit (≤20). Exiting."
    exit 0
fi

echo "⚠️  File count exceeds limit. Starting consolidation..."

# 3. Merge related topic files
merge_topic() {
    local TOPIC=$1
    local PATTERN=$2
    local OUTPUT=$MEMORY_DIR/${TOPIC}_CONSOLIDATED_${TIMESTAMP}.md

    echo "Merging $TOPIC files..."

    # Find files matching pattern
    find $MEMORY_DIR -maxdepth 1 -name "*${PATTERN}*.md" -type f | sort | while read file; do
        filename=$(basename "$file" .md)
        if [[ "$filename" == *CONSOLIDATED* ]] || [ "$filename" = "MEMORY" ]; then
            continue
        fi

        echo "  Adding: $filename.md"
    done > /tmp/files_to_merge.txt

    local file_count=$(wc -l < /tmp/files_to_merge.txt)
    if [ $file_count -eq 0 ]; then
        echo "  No files to merge for pattern: $PATTERN"
        return
    fi

    # Create consolidated file
    echo "# $TOPIC - Consolidated $(date +%Y-%m-%d)" > $OUTPUT
    echo "" >> $OUTPUT
    echo "**Consolidated from $file_count files**" >> $OUTPUT
    echo "" >> $OUTPUT

    # Append each file
    find $MEMORY_DIR -maxdepth 1 -name "*${PATTERN}*.md" -type f | sort | while read file; do
        filename=$(basename "$file" .md)
        if [[ "$filename" == *CONSOLIDATED* ]] || [ "$filename" = "MEMORY" ]; then
            continue
        fi

        echo "## $(basename $file .md)" >> $OUTPUT
        echo "" >> $OUTPUT
        cat "$file" >> $OUTPUT
        echo "" >> $OUTPUT
        echo "---" >> $OUTPUT
        echo "" >> $OUTPUT

        # Move original to archive
        mv "$file" $ARCHIVE_DIR/
        echo "  Archived: $filename.md"
    done

    echo "✅ Merged $file_count files into $(basename $OUTPUT)"
}

# 4. Execute merges (most common patterns)
echo ""
echo "=== Merging by topic ==="

merge_topic "PHASE" "PHASE_"
merge_topic "FEEDBACK" "feedback_"
merge_topic "ARCHITECTURE" "_ARCHITECTURE"
merge_topic "INTELLIGENCE" "_INTELLIGENCE"
merge_topic "SECURITY" "SECURITY"
merge_topic "ML" "ML_"
merge_topic "TELEGRAM" "TELEGRAM"
merge_topic "GSD" "GSD"
merge_topic "BRICK" "BRICK"
merge_topic "SENTINEL" "SENTINEL"

# 5. Keep only essential files
echo ""
echo "=== Filtering essential files ==="

ESSENTIAL_FILES=("MEMORY.md" "KEY_LEARNINGS.md" "MILESTONE_ARCHIVE.md")
KEPT_FILES=()

for file in $MEMORY_DIR/*.md; do
    [ -f "$file" ] || continue

    basename=$(basename "$file")
    keep=false

    # Check if essential
    for essential in "${ESSENTIAL_FILES[@]}"; do
        if [ "$basename" = "$essential" ]; then
            keep=true
            break
        fi
    done

    # Check if consolidated (keep these)
    if [[ "$basename" == *CONSOLIDATED* ]]; then
        keep=true
    fi

    if [ "$keep" = true ]; then
        KEPT_FILES+=("$basename")
    else
        echo "📦 Archiving: $basename"
        mv "$file" $ARCHIVE_DIR/
    fi
done

# 6. Update MEMORY.md index
echo ""
echo "=== Updating MEMORY.md index ==="

echo "# BMS Intelligence Project Memory - CONCISE INDEX" > $MEMORY_DIR/MEMORY.md
echo "" >> $MEMORY_DIR/MEMORY.md
echo "**Last Updated**: $(date +%Y-%m-%d) | **Status**: Active consolidation" >> $MEMORY_DIR/MEMORY.md
echo "" >> $MEMORY_DIR/MEMORY.md
echo "## Memory Management" >> $MEMORY_DIR/MEMORY.md
echo "" >> $MEMORY_DIR/MEMORY.md
echo "This index maintained by automated consolidation. Files archived to: \`$ARCHIVE_DIR\`" >> $MEMORY_DIR/MEMORY.md
echo "" >> $MEMORY_DIR/MEMORY.md
echo "## Active Files ($((${#KEPT_FILES[@]} - 1)))" >> $MEMORY_DIR/MEMORY.md  # -1 for MEMORY.md itself
echo "" >> $MEMORY_DIR/MEMORY.md

for file in "${KEPT_FILES[@]}"; do
    if [ "$file" != "MEMORY.md" ]; then
        echo "- \`$file\`" >> $MEMORY_DIR/MEMORY.md
    fi
done

# 7. Final report
echo ""
echo "=== CONSOLIDATION COMPLETE ==="
echo "Kept files:"
for file in "${KEPT_FILES[@]}"; do
    echo "  - $file"
done

echo ""
echo "Archived to: $ARCHIVE_DIR"
echo "Total files before: $FILE_COUNT"
echo "Total files after: ${#KEPT_FILES[@]}"

# 8. Check size limits
TOTAL_SIZE=$(du -sk $MEMORY_DIR 2>/dev/null | cut -f1 || echo "0")
ESTIMATED_TOKENS=$((TOTAL_SIZE * 4))

echo ""
echo "Size check:"
echo "- Total size: ${TOTAL_SIZE}KB"
echo "- Estimated tokens: ${ESTIMATED_TOKENS}"

if [ $ESTIMATED_TOKENS -gt 25000 ]; then
    echo "⚠️  WARNING: Memory still large (>25k tokens)"
    echo "   Consider:"
    echo "   1. Truncate consolidated files: head -200"
    echo "   2. Archive older consolidated files"
fi

echo ""
echo "✅ Consolidation complete!"
