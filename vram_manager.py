#!/usr/bin/env python
"""VRAM Model Manager - Check and clear models from GPU memory."""
import argparse
import json
import logging
import subprocess
import sys
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

# Configure logging for library use
logger = logging.getLogger(__name__)

def get_gpu_info() -> Optional[Dict[str, Any]]:
    """Get GPU memory information using nvidia-smi (multi-GPU via XML).

    Uses ``nvidia-smi -q -x`` and parses the XML output to support multiple GPUs.
    Returns both per-GPU information and an aggregate summary for backwards
    compatibility.

    Returns:
        Dict with keys:
            - ``gpus``: list of per-GPU dicts, each containing:
                ``index``, ``id``, ``name``, ``total_mb``, ``used_mb``,
                ``free_mb``, ``utilization``
            - ``aggregate``: dict with summed ``total_mb``, ``used_mb``,
              ``free_mb`` and max ``utilization``
            - Top-level compatibility keys: ``name``, ``total_mb``,
              ``used_mb``, ``free_mb``, ``utilization``
        or None if nvidia-smi fails.
    """
    try:
        result = subprocess.run(
            ["nvidia-smi", "-q", "-x"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not result.stdout:
            return None

        root = ET.fromstring(result.stdout)
        gpus: List[Dict[str, Any]] = []

        for idx, gpu in enumerate(root.findall(".//gpu")):
            name = gpu.findtext("product_name", default="GPU")

            total_str = gpu.findtext("fb_memory_usage/total") or ""
            used_str = gpu.findtext("fb_memory_usage/used") or ""
            free_str = gpu.findtext("fb_memory_usage/free") or ""

            def _to_mb(val: str) -> int:
                try:
                    return int(val.split()[0])
                except Exception:
                    return 0

            total_mb = _to_mb(total_str)
            used_mb = _to_mb(used_str)
            free_mb = _to_mb(free_str) if free_str else max(0, total_mb - used_mb)

            util_str = gpu.findtext("utilization/gpu") or "0"
            try:
                utilization = int(util_str.split()[0])
            except Exception:
                utilization = 0

            gpus.append(
                {
                    "index": idx,
                    "id": gpu.get("id"),
                    "name": name,
                    "total_mb": total_mb,
                    "used_mb": used_mb,
                    "free_mb": free_mb,
                    "utilization": utilization,
                }
            )

        if not gpus:
            return None

        agg_total = sum(g["total_mb"] for g in gpus)
        agg_used = sum(g["used_mb"] for g in gpus)
        agg_free = sum(g["free_mb"] for g in gpus)
        agg_util = max((g["utilization"] for g in gpus), default=0)

        aggregate = {
            "total_mb": agg_total,
            "used_mb": agg_used,
            "free_mb": agg_free,
            "utilization": agg_util,
        }

        # Backwards-compatible top-level keys use aggregate values.
        first_name = gpus[0]["name"]
        return {
            "gpus": gpus,
            "aggregate": aggregate,
            "name": first_name,
            "total_mb": agg_total,
            "used_mb": agg_used,
            "free_mb": agg_free,
            "utilization": agg_util,
        }
    except (subprocess.SubprocessError, OSError, ET.ParseError, ValueError) as e:
        logger.warning("Error getting GPU info: %s", e)
    return None

def get_ollama_models() -> List[Dict[str, str]]:
    """Get list of models loaded in Ollama.

    Returns:
        List of dictionaries with model info (name, id, size, processor).
    """
    try:
        result = subprocess.run(['ollama', 'ps'], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            models: List[Dict[str, str]] = []
            for line in lines[1:]:  # Skip header
                parts = line.split()
                if parts:
                    models.append({
                        'name': parts[0],
                        'id': parts[1] if len(parts) > 1 else '',
                        'size': parts[2] if len(parts) > 2 else '',
                        'processor': parts[3] if len(parts) > 3 else ''
                    })
            return models
    except (subprocess.SubprocessError, OSError) as e:
        logger.warning("Error getting Ollama models: %s", e)
    return []

def get_available_ollama_models() -> List[Dict[str, str]]:
    """Get list of all available Ollama models.

    Returns:
        List of dictionaries with model info (name, id, size).
    """
    try:
        result = subprocess.run(['ollama', 'list'], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            models: List[Dict[str, str]] = []
            for line in lines[1:]:  # Skip header
                parts = line.split()
                if parts:
                    models.append({
                        'name': parts[0],
                        'id': parts[1] if len(parts) > 1 else '',
                        'size': parts[2] if len(parts) > 2 else ''
                    })
            return models
    except (subprocess.SubprocessError, OSError) as e:
        logger.warning("Error listing Ollama models: %s", e)
    return []

def stop_ollama_model(model_name: str) -> Tuple[bool, str]:
    """Stop/unload an Ollama model from memory.

    Args:
        model_name: Name of the model to stop.

    Returns:
        Tuple of (success, error_message).
    """
    try:
        result = subprocess.run(['ollama', 'stop', model_name], capture_output=True, text=True, check=False)
        return result.returncode == 0, result.stderr
    except (subprocess.SubprocessError, OSError) as e:
        return False, str(e)

def get_gpu_processes() -> List[Dict[str, str]]:
    """Get processes using the GPU.

    Returns:
        List of dictionaries with process info (pid, name, memory).
    """
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-compute-apps=pid,process_name,used_memory',
             '--format=csv,noheader'],
            capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            processes: List[Dict[str, str]] = []
            for line in result.stdout.strip().split('\n'):
                if line and 'Insufficient Permissions' not in line and '[N/A]' not in line:
                    parts = line.split(', ')
                    if len(parts) >= 3:
                        processes.append({
                            'pid': parts[0].strip(),
                            'name': parts[1].strip(),
                            'memory': parts[2].strip()
                        })
            return processes
    except (subprocess.SubprocessError, OSError) as e:
        logger.warning("Error getting GPU processes: %s", e)
    return []

def display_status() -> None:
    """Display current VRAM and model status."""
    print("\n" + "=" * 60)
    print("VRAM MODEL MANAGER")
    print("=" * 60)

    # GPU Info
    gpu_info = get_gpu_info()
    if gpu_info:
        used_pct = (gpu_info['used_mb'] / gpu_info['total_mb']) * 100
        print(f"\nGPU: {gpu_info['name']}")
        print(f"VRAM: {gpu_info['used_mb']:,} MB / {gpu_info['total_mb']:,} MB ({used_pct:.1f}% used)")
        print(f"Free: {gpu_info['free_mb']:,} MB")
        print(f"Utilization: {gpu_info['utilization']}%")

    # Ollama Models
    print("\n" + "-" * 40)
    print("LOADED OLLAMA MODELS:")
    print("-" * 40)
    models = get_ollama_models()
    if models:
        for m in models:
            print(f"  - {m['name']} ({m['size']}) [{m['processor']}]")
        print(f"\nTo unload: python vram_manager.py --stop <model_name>")
    else:
        print("  No Ollama models currently loaded in VRAM")

    # GPU Processes
    print("\n" + "-" * 40)
    print("GPU PROCESSES:")
    print("-" * 40)
    processes = get_gpu_processes()
    if processes:
        for p in processes:
            name = p['name'].split('\\')[-1] if '\\' in p['name'] else p['name']
            print(f"  PID {p['pid']}: {name} - {p['memory']}")
    else:
        print("  No user GPU processes found (or permissions required)")

    print("\n" + "=" * 60)

def main() -> None:
    """CLI entry point for VRAM Model Manager."""
    parser = argparse.ArgumentParser(description='VRAM Model Manager')
    parser.add_argument('--status', '-s', action='store_true', help='Show status (default)')
    parser.add_argument('--stop', metavar='MODEL', help='Stop/unload an Ollama model')
    parser.add_argument('--stop-all', action='store_true', help='Stop all loaded Ollama models')
    parser.add_argument('--list', '-l', action='store_true', help='List available Ollama models')
    parser.add_argument('--json', '-j', action='store_true', help='Output as JSON')

    args = parser.parse_args()

    if args.json:
        data = {
            'gpu': get_gpu_info(),
            'loaded_models': get_ollama_models(),
            'gpu_processes': get_gpu_processes()
        }
        print(json.dumps(data, indent=2))
        return

    if args.stop:
        print(f"Stopping Ollama model: {args.stop}")
        success, error = stop_ollama_model(args.stop)
        if success:
            print(f"Successfully unloaded {args.stop}")
        else:
            print(f"Failed to unload {args.stop}: {error}")
        display_status()
        return

    if args.stop_all:
        models = get_ollama_models()
        if not models:
            print("No models currently loaded")
        else:
            for m in models:
                print(f"Stopping {m['name']}...")
                success, error = stop_ollama_model(m['name'])
                if success:
                    print(f"  Unloaded {m['name']}")
                else:
                    print(f"  Failed: {error}")
        display_status()
        return

    if args.list:
        print("\nAvailable Ollama Models:")
        print("-" * 40)
        models = get_available_ollama_models()
        for m in models:
            print(f"  {m['name']} ({m['size']})")
        return

    # Default: show status
    display_status()

if __name__ == "__main__":
    main()
