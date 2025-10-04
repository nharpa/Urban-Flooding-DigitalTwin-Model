
from typing import List, Iterable
from digital_twin.database.database_utils import FloodingDatabase
from digital_twin.services import risk_algorithm
from datetime import datetime
from pathlib import Path


def _iter_catchments(db: FloodingDatabase) -> Iterable[dict]:
    """Yield all catchment documents (business fields only)."""
    for doc in db.list_catchments():
        yield doc


def run_batch_simulation(
    rain_mmhr: List[float],
    timestamps_utc: List[str],
    *,
    print_header: bool = True,
    output_file: str | None = None,
    append: bool = False,
) -> str:
    """Run the simulation across all catchments and print results.

    Parameters
    ----------
    rain_mmhr : List[float]
        Rainfall intensities (mm/hr) aligned with timestamps.
    timestamps_utc : List[str]
        ISO 8601 UTC timestamps (same length as rain_mmhr).
    print_header : bool, default True
        Whether to also echo a header to console.
    output_file : str | None, default None
        Path to a text file to write the same lines that are printed. If
        None, a timestamped file name under `./simulation_outputs/` will
        be created.
    append : bool, default False
        If True and output_file exists, append instead of overwrite.

    Returns
    -------
    str
        The path of the output text file written.
    """
    if len(rain_mmhr) != len(timestamps_utc):
        raise ValueError("rain_mmhr and timestamps_utc must be same length")

    # Determine output file path
    if output_file is None:
        out_dir = Path("simulation_outputs")
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        output_file = str(out_dir / f"batch_sim_{stamp}.txt")

    mode = "a" if append else "w"
    lines: List[str] = []

    def emit(line: str):
        print(line)
        lines.append(line)

    db = FloodingDatabase()
    catchments = list(_iter_catchments(db))
    if print_header:
        emit("=== Batch Catchment Simulation ===")
        emit(f"Catchments found: {len(catchments)}")
        emit(
            f"Timesteps: {len(rain_mmhr)} (from {timestamps_utc[0]} to {timestamps_utc[-1]})")
        emit("Rain (mm/hr): " + ", ".join(str(x) for x in rain_mmhr))
        emit("----------------------------------")

    for c in catchments:
        cid = c.get("catchment_id", "UNKNOWN")
        name = c.get("name", "(no-name)")
        C = float(c.get("C", 0.0))
        A_km2 = float(c.get("A_km2", 0.0))
        Qcap_m3s = float(c.get("Qcap_m3s", 0.0))
        emit(
            f"\n>>> Catchment {cid} - {name} | C={C} A_km2={A_km2} Qcap_m3s={Qcap_m3s}")

        sim = risk_algorithm.simulate_catchment(
            rain_mmhr, timestamps_utc, C, A_km2, Qcap_m3s)
        # Print each timestep row as requested
        for row in sim["series"]:
            emit(
                "t={t} i={i}mm/hr Qrunoff={Qrunoff}m3/s L={L} R={R}".format(
                    **row)
            )
        emit(f"Max risk for {cid}: {sim['max_risk']}")

    db.close()
    # Write collected lines
    with open(output_file, mode, encoding="utf-8") as f:
        for ln in lines:
            f.write(ln + "\n")
    emit(f"\nOutput written to: {output_file}")
    return output_file


def _demo_run():  # pragma: no cover - helper for manual execution
    rain_mmhr = [0.1, 0.2, 0.2, 0.1, 0.0, 0.0]
    timestamps_utc = [
        "2025-09-25T00:00:00Z",
        "2025-09-25T01:00:00Z",
        "2025-09-25T02:00:00Z",
        "2025-09-25T03:00:00Z",
        "2025-09-25T04:00:00Z",
        "2025-09-25T05:00:00Z",
    ]
    run_batch_simulation(rain_mmhr, timestamps_utc, output_file=None)


if __name__ == "__main__":  # pragma: no cover
    _demo_run()
