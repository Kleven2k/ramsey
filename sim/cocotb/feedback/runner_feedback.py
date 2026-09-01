import os
import sys
import subprocess
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SIM_DIR   = Path(__file__).resolve().parent
RTL_DIR   = REPO_ROOT / "rtl" / "feedback"
SIM_BUILD = SIM_DIR / "sim_build_feedback"

MODULES = [
    {
        "name":    "state_discriminator",
        "sources": [
            RTL_DIR / "state_discriminator.sv",
            SIM_DIR / "state_discriminator_tb_wrapper.sv",
        ],
        "top":     "state_discriminator_tb_wrapper",
        "vvp":     SIM_BUILD / "sim_disc.vpp",
        "filter":  "test_disc",
    },
    {
        "name":    "feedback_ctrl",
        "sources": [
            RTL_DIR / "feedback_ctrl.sv",
            SIM_DIR / "feedback_ctrl_tb_wrapper.sv",
        ],
        "top":     "feedback_ctrl_tb_wrapper",
        "vvp":     SIM_BUILD / "sim_fb.vpp",
        "filter":  "test_fb",
    },
    {
        "name":    "latency_counter",
        "sources": [
            RTL_DIR / "latency_counter.sv",
            SIM_DIR / "latency_counter_tb_wrapper.sv",
        ],
        "top":     "latency_counter_tb_wrapper",
        "vvp":     SIM_BUILD / "sim_lc.vpp",
        "filter":  "test_lc",
    },
]


def get_cocotb_env():
    cocotb_config = shutil.which("cocotb-config")
    libpython = subprocess.check_output(
        [cocotb_config, "--libpython"], text=True
    ).strip()
    base_python_home = str(Path(libpython).parent)
    venv_python = sys.executable
    cocotb_libs = Path(venv_python).parents[1] / "Lib" / "site-packages" / "cocotb" / "libs"
    env = os.environ.copy()
    env["PYTHONHOME"]       = base_python_home
    env["PYGPI_PYTHON_BIN"] = venv_python
    env["PYTHONPATH"]       = str(SIM_DIR)
    env["PATH"]             = base_python_home + os.pathsep + env.get("PATH", "")
    return env, cocotb_libs


def compile_module(mod):
    print(f"\n=== Compiling {mod['name']} ===")
    SIM_BUILD.mkdir(exist_ok=True)
    cmd = [
        "iverilog", "-g2012",
        f"-I{RTL_DIR}",
        "-o", str(mod["vvp"]),
        "-s", mod["top"],
    ] + [str(s) for s in mod["sources"]]
    r = subprocess.run(cmd, cwd=REPO_ROOT)
    if r.returncode != 0:
        print(f"COMPILE FAILED: {mod['name']}")
        sys.exit(1)


def run_module(mod, env, cocotb_libs):
    print(f"\n=== Running {mod['name']} ===")
    e = env.copy()
    e["COCOTB_TEST_MODULES"] = "test_feedback"
    e["COCOTB_TEST_FILTER"]  = mod["filter"]
    cmd = [
        "vvp",
        "-M", str(cocotb_libs),
        "-m", "cocotbvpi_icarus",
        str(mod["vvp"]),
    ]
    subprocess.run(cmd, env=e, cwd=SIM_DIR)


if __name__ == "__main__":
    env, cocotb_libs = get_cocotb_env()
    target = sys.argv[1] if len(sys.argv) > 1 else None

    for mod in MODULES:
        if target and target not in mod["name"]:
            continue
        compile_module(mod)
        run_module(mod, env, cocotb_libs)