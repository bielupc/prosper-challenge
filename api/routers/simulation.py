import asyncio

from core.scenarios import list_scenarios
from core.simulation import create_runner, get_runner, reset_simulation_data
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from schemas.simulation import SimulationRequest, SimulationResult

router = APIRouter()

@router.get("/simulate/scenarios")
async def get_scenarios():
    return list_scenarios()


@router.post("/simulate/run", response_model=dict)
async def run_simulation(body: SimulationRequest):
    try:
        runner = create_runner(body.scenario_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    # Run in the background so the client can stream events. 
    runner.task = asyncio.create_task(runner.run())
    return {"sim_id": runner.id, "status": "started"}


@router.get("/simulate/stream/{sim_id}")
async def stream_simulation(sim_id: str):
    runner = get_runner(sim_id)
    if not runner:
        raise HTTPException(status_code=404, detail="Simulation not found")

    async def wrapped():
        async for chunk in runner.event_stream():
            yield chunk
            await asyncio.sleep(0)

    return StreamingResponse(
        wrapped(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/simulate/result/{sim_id}", response_model=SimulationResult)
async def get_result(sim_id: str):
    runner = get_runner(sim_id)
    if not runner:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return runner.result


@router.post("/simulate/reset")
async def reset_simulation():
    return await reset_simulation_data()
