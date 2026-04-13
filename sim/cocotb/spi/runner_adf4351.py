import os
import sys
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SIM_DIR   = Path(__file__).resolve().parent

SOURCES = [
    REPO_ROOT / "rtl" / "spi" / "spi_master.sv",
    REPO_ROOT / "rtl" / "spi" / "adf4351_ctrl.sv",
    SIM_DIR   / "adf4351_tb_wrapper.sv",
]

SIM_BUILD = SIM_DIR / "sim_build_spi"
VVP_FILE  = SIM_BUILD / "sim_adf4351.vpp"

def compile():
    print("\n=== Compiling ===\n")
    SIM_BUILD.mkdir(exist_ok=True)

    cmd = [
        "iverilog", "-g2012",
        "-o", str(VVP_FILE),
        "-s", "adf4351_tb_wrapper",
    ] + [str(s) for s in SOURCES]

    r = subprocess.run(cmd, cwd=REPO_ROOT)
    if r.returncode != 0:
        print("COMPILE FAILED")
        sys.exit(1)

def run(testcase=None):
    print("\n=== Running simulation ===")

    import shutil
    cocotb_config = shutil.which("cocotb-config")
    libpython = subprocess.check_output(
        [cocotb_config, "--libpython"], text=True
    ).strip()
    base_python_home = str(Path(libpython).parent)

    venv_python = sys.executable
    cocotb_libs = Path(venv_python).parents[1] / "Lib" / "site-packages" / "cocotb" / "libs"

    env = os.environ.copy()
    env["PYTHONHOME"]          = base_python_home
    env["PYGPI_PYTHON_BIN"]    = venv_python
    env["PYTHONPATH"]          = str(SIM_DIR)
    env["COCOTB_TEST_MODULES"] = "test_adf4351"
    env["PATH"]                = base_python_home + os.pathsep + env.get("PATH", "")

    if testcase:
        env["COCOTB_TEST_FILTER"] = testcase

    print(f"SIM_DIR:    {SIM_DIR}")
    print(f"PYTHONHOME: {base_python_home}")

    cmd = [
        "vvp",
        "-M", str(cocotb_libs),
        "-m", "cocotbvpi_icarus",
        str(VVP_FILE),
    ]
    subprocess.run(cmd, env=env, cwd=SIM_DIR)

if __name__ == "__main__":
    testcase = sys.argv[1] if len(sys.argv) > 1 else None
    compile()
    run(testcase)
