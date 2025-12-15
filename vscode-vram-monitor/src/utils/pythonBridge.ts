import { spawn } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';

export interface PythonPaths {
    pythonPath: string;
    vramManagerPath: string;
}

export interface ExecutionOptions {
    timeout?: number;
    cwd?: string;
}

export class PythonBridgeError extends Error {
    public readonly stderr?: string;

    constructor(message: string, stderr?: string) {
        super(message);
        this.stderr = stderr;
        this.name = 'PythonBridgeError';
    }
}

export class PythonNotFoundError extends PythonBridgeError {
    constructor(pythonPath: string) {
        super(`Python executable not found: ${pythonPath}`);
        this.name = 'PythonNotFoundError';
    }
}

export class VRAMManagerNotFoundError extends PythonBridgeError {
    constructor(scriptPath: string) {
        super(`VRAM manager script not found: ${scriptPath}`);
        this.name = 'VRAMManagerNotFoundError';
    }
}

export class ExecutionTimeoutError extends PythonBridgeError {
    constructor(timeout: number) {
        super(`Python script execution timed out after ${timeout}ms`);
        this.name = 'ExecutionTimeoutError';
    }
}

function fileExists(scriptPath: string): boolean {
    try {
        return fs.existsSync(scriptPath);
    } catch {
        return false;
    }
}

export async function executePythonScript(
    paths: PythonPaths,
    args: string[] = [],
    options: ExecutionOptions = {}
): Promise<string> {
    const timeout = options.timeout ?? 5000;
    const cwd = options.cwd ?? path.dirname(paths.vramManagerPath);

    if (!fileExists(paths.vramManagerPath)) {
        throw new VRAMManagerNotFoundError(paths.vramManagerPath);
    }

    return new Promise((resolve, reject) => {
        let stdout = '';
        let stderr = '';
        let killed = false;

        const process = spawn(paths.pythonPath, [paths.vramManagerPath, ...args], {
            cwd,
            shell: true,
            windowsHide: true
        });

        const timeoutId = setTimeout(() => {
            killed = true;
            process.kill('SIGTERM');
            reject(new ExecutionTimeoutError(timeout));
        }, timeout);

        process.stdout.on('data', (data: Buffer) => {
            stdout += data.toString();
        });

        process.stderr.on('data', (data: Buffer) => {
            stderr += data.toString();
        });

        process.on('error', (err: NodeJS.ErrnoException) => {
            clearTimeout(timeoutId);
            if (err.code === 'ENOENT') {
                reject(new PythonNotFoundError(paths.pythonPath));
            } else {
                reject(new PythonBridgeError(`Failed to spawn Python process: ${err.message}`, stderr));
            }
        });

        process.on('close', (code: number | null) => {
            clearTimeout(timeoutId);
            if (killed) {
                return;
            }
            if (code === 0) {
                resolve(stdout.trim());
            } else {
                reject(new PythonBridgeError(`Python script exited with code ${code}`, stderr || undefined));
            }
        });
    });
}

export async function fetchVRAMDataRaw(paths: PythonPaths, options?: ExecutionOptions): Promise<string> {
    return executePythonScript(paths, ['--json'], options);
}
