#!/usr/bin/env python
"""VRAM Model Manager - Check and clear models from GPU memory"""
import subprocess
import json
import sys
import argparse

def get_gpu_info():
    """Get GPU memory information using nvidia-smi"""
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu',
             '--format=csv,noheader,nounits'],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(', ')
            if len(parts) >= 5:
                return {
                    'name': parts[0],
                    'total_mb': int(parts[1]),
                    'used_mb': int(parts[2]),
                    'free_mb': int(parts[3]),
                    'utilization': int(parts[4])
                }
    except Exception as e:
        print(f"Error getting GPU info: {e}")
    return None

def get_ollama_models():
    """Get list of models loaded in Ollama"""
    try:
        result = subprocess.run(['ollama', 'ps'], capture_output=True, text=True)
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            models = []
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
    except Exception as e:
        print(f"Error getting Ollama models: {e}")
    return []

def get_available_ollama_models():
    """Get list of all available Ollama models"""
    try:
        result = subprocess.run(['ollama', 'list'], capture_output=True, text=True)
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            models = []
            for line in lines[1:]:  # Skip header
                parts = line.split()
                if parts:
                    models.append({
                        'name': parts[0],
                        'id': parts[1] if len(parts) > 1 else '',
                        'size': parts[2] if len(parts) > 2 else ''
                    })
            return models
    except Exception as e:
        print(f"Error listing Ollama models: {e}")
    return []

def stop_ollama_model(model_name):
    """Stop/unload an Ollama model from memory"""
    try:
        result = subprocess.run(['ollama', 'stop', model_name], capture_output=True, text=True)
        return result.returncode == 0, result.stderr
    except Exception as e:
        return False, str(e)

def get_gpu_processes():
    """Get processes using the GPU"""
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-compute-apps=pid,process_name,used_memory',
             '--format=csv,noheader'],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            processes = []
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
    except Exception as e:
        print(f"Error getting GPU processes: {e}")
    return []

def display_status():
    """Display current VRAM and model status"""
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

def main():
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
