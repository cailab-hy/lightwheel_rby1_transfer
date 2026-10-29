#!/usr/bin/env bash
# Evaluate a SmolVLA checkpoint on T1..T10 (default) or the tasks given with --tasks, 50 fixed seeds each.
#   ./vla_lab/eval_smolvla.sh --policy-path <RUN_FOLDER>/checkpoints/last/pretrained_model --output <EVAL_DIR>
#   ./vla_lab/eval_smolvla.sh --policy-path ... --output ... --tasks "T1 T4" --episodes 3
# Every other option is passed to vla_lab/scripts/eval_smolvla.py (see --help there).
set -euo pipefail
RBY_PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$RBY_PROJECT_DIR/vla_lab/scripts${PYTHONPATH:+:$PYTHONPATH}"
TASKS="T1 T2 T3 T4 T5 T6 T7 T8 T9 T10"
OUTPUT=""
ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --tasks) TASKS="$2"; shift 2 ;;
        --output) OUTPUT="$2"; ARGS+=("$1" "$2"); shift 2 ;;
        *) ARGS+=("$1"); shift ;;
    esac
done
[[ -n "$OUTPUT" ]] || { echo "--output is required" >&2; exit 2; }
for T in $TASKS; do
    "$RBY_PROJECT_DIR/run_python.sh" "$RBY_PROJECT_DIR/vla_lab/scripts/eval_smolvla.py" --task "$T" "${ARGS[@]}" \
        2>&1 | grep --line-buffered -E "^(POLICY|\[T|TASK_SUMMARY)|Error|Traceback" || true
    [[ -f "$OUTPUT/$T/summary.json" ]] || { echo "evaluation of $T failed (no $OUTPUT/$T/summary.json)" >&2; exit 1; }
done
"$RBY_PROJECT_DIR/run_python.sh" "$RBY_PROJECT_DIR/vla_lab/scripts/eval_summary.py" --output "$OUTPUT"
