import logging
from typing import Tuple, Optional, Union

from src.eval_utils_gpt_express import (
    explore_step,
    call_openai_api,
    encode_tensor2base64,
)
from src.tsdf_planner import TSDFPlanner, SnapShot, Frontier
from src.scene_aeqa import Scene


def query_vlm_for_response(
    question: str,
    scene: Scene,
    tsdf_planner: TSDFPlanner,
    rgb_egocentric_views: list,
    cfg,
    verbose: bool = False,
) -> Optional[Tuple[Union[SnapShot, Frontier], str, int]]:
    # prepare input for vlm
    step_dict = {}

    # prepare snapshots
    object_id_to_name = {
        obj_id: obj["class_name"] for obj_id, obj in scene.objects.items()
    }
    step_dict["obj_map"] = object_id_to_name

    step_dict["snapshot_objects"] = {}
    step_dict["snapshot_imgs"] = {}
    for rgb_id, snapshot in scene.snapshots.items():
        step_dict["snapshot_objects"][rgb_id] = snapshot.cluster
        step_dict["snapshot_imgs"][rgb_id] = scene.all_observations[rgb_id]

    # prepare frontier
    step_dict["frontier_imgs"] = [
        frontier.feature for frontier in tsdf_planner.frontiers
    ]

    # prepare egocentric views
    if cfg.egocentric_views:
        step_dict["egocentric_views"] = rgb_egocentric_views
        step_dict["use_egocentric_views"] = True

    # prepare question
    step_dict["question"] = question

    # query vlm
    outputs, snapshot_id_mapping, reason, n_filtered_snapshots = explore_step(
        step_dict, cfg, verbose=verbose
    )
    if outputs is None:
        logging.error(f"explore_step failed and returned None")
        return None
    logging.info(f"Response: [{outputs}]\nReason: [{reason}]")

    # parse returned results
    try:
        target_type, target_index = outputs.split(" ")[0], outputs.split(" ")[1]
        logging.info(f"Prediction: {target_type}, {target_index}")
    except:
        logging.info(f"Wrong output format, failed!")
        return None

    if target_type not in ["snapshot", "frontier"]:
        logging.info(f"Wrong target type: {target_type}, failed!")
        return None

    if target_type == "snapshot":
        if int(target_index) < 0 or int(target_index) >= len(snapshot_id_mapping):
            logging.info(
                f"Target index can not match real objects: {target_index}, failed!"
            )
            return None
        target_index = snapshot_id_mapping[int(target_index)]
        logging.info(f"The index of target snapshot {target_index}")

        # get the target snapshot
        if target_index < 0 or target_index >= len(scene.snapshots):
            logging.info(
                f"Predicted snapshot target index out of range: {target_index}, failed!"
            )
            return None

        pred_target_snapshot = list(scene.snapshots.values())[target_index]
        logging.info(
            "Pred_target_class: "
            + str(
                " ".join(
                    [
                        object_id_to_name[obj_id]
                        for obj_id in pred_target_snapshot.cluster
                    ]
                )
            )
        )
        logging.info(f"Next choice Snapshot of {pred_target_snapshot.image}")

        return pred_target_snapshot, reason, n_filtered_snapshots
    else:  # target_type == "frontier"
        target_index = int(target_index)
        if target_index < 0 or target_index >= len(tsdf_planner.frontiers):
            logging.info(
                f"Predicted frontier target index out of range: {target_index}, failed!"
            )
            return None
        target_point = tsdf_planner.frontiers[target_index].position
        logging.info(f"Next choice: Frontier at {target_point}")
        pred_target_frontier = tsdf_planner.frontiers[target_index]

        return pred_target_frontier, reason, n_filtered_snapshots


def answer_express_question(question: str, rgb_image):
    """Answer an EXPRESS question from SCOPE's last observation when needed."""
    prompt = (
        "Answer the indoor-scene question using only the provided observation. "
        "Be concise and provide the answer directly; do not describe your reasoning.\n"
        f"Question: {question}\nAnswer:"
    )
    contents = [(prompt, encode_tensor2base64(rgb_image))] if rgb_image is not None else [(prompt,)]
    response = call_openai_api("You are a careful embodied-question-answering agent.", contents)
    return response.strip() if response else ""


def judge_express_answer(question: str, reference_answer: str, prediction: str):
    """Return the EXPRESS-compatible (0-5 quality, 0/1 correct) local judgement."""
    prompt = (
        "You are grading an embodied QA response. Compare the prediction to the reference. "
        "Return exactly two comma-separated numbers: a quality score from 0 to 5, then "
        "a correctness flag (1 only if the prediction answers the question consistently with the reference, else 0).\n"
        f"Question: {question}\nReference: {reference_answer}\nPrediction: {prediction}\nGrade:"
    )
    raw = call_openai_api("You are a strict benchmark evaluator.", [(prompt,)])
    if not raw:
        return None, None, ""
    try:
        first = raw.strip().splitlines()[0].replace("Grade:", "").strip()
        score_text, correct_text = [part.strip() for part in first.split(",")[:2]]
        score = float(score_text)
        correct = int(correct_text)
        if not (0.0 <= score <= 5.0 and correct in (0, 1)):
            raise ValueError("out-of-range grade")
        return score, correct, raw.strip()
    except Exception:
        logging.warning("Unparseable EXPRESS local judgement: %r", raw)
        return None, None, raw.strip()
