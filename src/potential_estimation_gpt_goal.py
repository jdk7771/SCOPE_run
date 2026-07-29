import openai
from openai import OpenAI
from src.const import *
from src.vlm_timing import record_vlm_response
from typing import Optional
from PIL import Image
import io
import base64
import time
import os
import json
import logging
from typing import Dict, Sequence, Tuple

client = OpenAI(
    base_url=END_POINT,
    api_key=OPENAI_KEY,
)


def format_content(image, question_text, question_image_path):
    img_pil = Image.fromarray(image.astype('uint8'))
    with io.BytesIO() as output:
        img_pil.save(output, format="PNG")
        png_bytes = output.getvalue()
    frontier_image = base64.b64encode(png_bytes).decode("utf-8")

    # Read and encode the question image
    question_image = None
    if question_image_path is not None and os.path.exists(question_image_path):
        try:
            question_img_pil = Image.open(question_image_path)
            with io.BytesIO() as output:
                question_img_pil.save(output, format="PNG")
                question_png_bytes = output.getvalue()
            question_image = base64.b64encode(question_png_bytes).decode("utf-8")
        except Exception as e:
            print(f"Error loading question image: {e}")

    formated_content = []
    formated_content.append({"type": "text", "text": (
        "You are a semantic reasoning agent assisting a robot in navigation planning. "
        "The robot is considering the following **frontier observation** as a potential place to visit. You are also given the **goal question** and, if available, the **goal image**. Your task is to analyze whether exploring this frontier would help the robot achieve its goal.\n\n"
        "Analyze the frontier image and provide ratings for each criterion. Use EXACTLY this format:\n\n"
        "**SEMANTIC_RICHNESS:** [Low/Medium/High]\n"
        "**EXPLORABILITY:** [Low/Medium/High]\n" 
        "**GOAL_RELEVANCE:** [Low/Medium/High]\n"
        "**POTENTIAL_SCORE:** [X.X] (where X.X is a number from 1.0 to 5.0)\n"
        "**EXPLANATION:** [Your reasoning in 2-3 sentences]\n\n"
        "Definitions:\n"
        "- Semantic richness: How many meaningful objects, structures, or environmental cues are visible?\n"
        "- Explorability: Does this lead to new regions, paths, or unexplored areas? Are there doors, corridors, stairs?\n"
        "- Goal relevance: Based on the goal, does this frontier likely contain or lead to the target?\n"
        "- Potential score: Overall value for exploration (1.0=very low, 3.0=medium, 5.0=very high)\n\n"
        "Example output:\n"
        "**SEMANTIC_RICHNESS:** High\n"
        "**EXPLORABILITY:** Medium\n"
        "**GOAL_RELEVANCE:** High\n"
        "**POTENTIAL_SCORE:** 4.2\n"
        "**EXPLANATION:** The image shows a hallway with several doorways leading to rooms with furniture. This is semantically rich and highly relevant for finding household objects."
    )})

    formated_content.append({"type": "text", "text": f"**Goal question**: {question_text}"})

    if question_image is not None:
        formated_content.append({"type": "text", "text": "**Goal image**:"})
        formated_content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{question_image}",
                    "detail": "high",
                },
            }
        )
    else:
        formated_content.append({"type": "text", "text": "**Goal image**: Not provided"})
    
    formated_content.append({"type": "text", "text": "**Frontier observation**:"})

    formated_content.append(
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{frontier_image}",
                "detail": "high",
            },
        }
    )
    return formated_content


# send information to openai
def get_potential_estimation(metadata, image) -> Optional[str]:
    rate_limit_retries = 0
    other_error_retries = 0
    max_rate_limit_retries = 30  # More generous for potential estimation
    max_other_error_retries = 15  # More retries for this critical function
    
    question_text = metadata['question']
    question_image_path = metadata['image'] if 'image' in metadata else None
    formated_content = format_content(image, question_text, question_image_path)
    message_text = [
        {"role": "user", "content": formated_content},
    ]
    
    while True:  # Keep trying indefinitely for rate limits
        attempt = rate_limit_retries + other_error_retries + 1
        request_start = time.perf_counter()
        try:
            completion = client.chat.completions.create(
                # model="gpt-4o-2024-11-20",
                model="gemma3:27b",
                messages=message_text,
                temperature=0.7,
                max_tokens=4096,
                top_p=0.95,
                frequency_penalty=0,
                presence_penalty=0,
            )
            record_vlm_response("frontier_potential", time.perf_counter() - request_start, success=True, attempt=attempt)
            return completion.choices[0].message.content
        except openai.RateLimitError as e:
            record_vlm_response("frontier_potential", time.perf_counter() - request_start, success=False, attempt=attempt, error_type=type(e).__name__)
            rate_limit_retries += 1
            wait_time = min(60 + (rate_limit_retries * 10), 300)  # Exponential backoff, max 5 minutes
            print(f"Rate limit error in potential estimation ({rate_limit_retries}), waiting {wait_time}s before retry...")
            time.sleep(wait_time)
            
            # If we've hit too many rate limits, give a longer break
            if rate_limit_retries >= max_rate_limit_retries:
                print(f"Hit {max_rate_limit_retries} rate limits, taking a 15-minute break...")
                time.sleep(900)  # 15 minute break
                rate_limit_retries = 0  # Reset counter after long break
            continue
        except (openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError) as e:
            record_vlm_response("frontier_potential", time.perf_counter() - request_start, success=False, attempt=attempt, error_type=type(e).__name__)
            other_error_retries += 1
            if other_error_retries > max_other_error_retries:
                print(f"Too many connection/timeout/server errors in potential estimation ({other_error_retries}), using default scores")
                return None  # Fallback to default scores in potential graph
            wait_time = min(30 + (other_error_retries * 15), 180)  # Exponential backoff, max 3 minutes
            print(f"API connection/timeout/server error in potential estimation ({other_error_retries}), waiting {wait_time}s before retry: {e}")
            time.sleep(wait_time)
            continue
        except openai.BadRequestError as e:
            record_vlm_response("frontier_potential", time.perf_counter() - request_start, success=False, attempt=attempt, error_type=type(e).__name__)
            print(f"Bad request error in potential estimation (likely permanent): {e}")
            return None
        except Exception as e:
            record_vlm_response("frontier_potential", time.perf_counter() - request_start, success=False, attempt=attempt, error_type=type(e).__name__)
            other_error_retries += 1
            if other_error_retries > max_other_error_retries:
                print(f"Too many unexpected errors in potential estimation ({other_error_retries}), using default scores: {e}")
                return None
            wait_time = min(30 + (other_error_retries * 15), 180)
            print(f"Unexpected error in potential estimation ({other_error_retries}), waiting {wait_time}s before retry: {e}")
            time.sleep(wait_time)
            continue


def _encode_image(image):
    """Encode one RGB frontier observation for an OpenAI-compatible request."""
    image_pil = Image.fromarray(image.astype("uint8"))
    with io.BytesIO() as output:
        image_pil.save(output, format="PNG")
        return base64.b64encode(output.getvalue()).decode("utf-8")


def _normalise_frontier_id(value):
    """Accept JSON IDs written as either ``3`` or ``F_3``."""
    if isinstance(value, str):
        value = value.strip()
        if value.lower().startswith("f_"):
            value = value[2:]
    return int(value)


def _normalise_level(value, field_name):
    level = str(value).strip().lower()
    levels = {"low": "Low", "medium": "Medium", "high": "High"}
    if level not in levels:
        raise ValueError(f"{field_name} must be Low, Medium, or High; got {value!r}")
    return levels[level]


def _result_to_potential_text(result):
    """Convert a batch JSON item into the legacy text parsed by PotentialGraph."""
    semantic_richness = _normalise_level(
        result["semantic_richness"], "semantic_richness"
    )
    explorability = _normalise_level(result["explorability"], "explorability")
    goal_relevance = _normalise_level(result["goal_relevance"], "goal_relevance")
    potential_score = float(result["potential_score"])
    if not 1.0 <= potential_score <= 5.0:
        raise ValueError(
            f"potential_score must be in [1.0, 5.0]; got {potential_score}"
        )
    explanation = str(result.get("explanation", "")).strip()
    if not explanation:
        raise ValueError("explanation is empty")
    return "\n".join(
        [
            f"**SEMANTIC_RICHNESS:** {semantic_richness}",
            f"**EXPLORABILITY:** {explorability}",
            f"**GOAL_RELEVANCE:** {goal_relevance}",
            f"**POTENTIAL_SCORE:** {potential_score:.2f}",
            f"**EXPLANATION:** {explanation}",
        ]
    )


def _parse_batch_response(response_text, requested_ids):
    """Parse strict batch JSON and return ``frontier_id -> legacy score text``.

    Invalid or missing items are deliberately omitted.  The caller leaves those
    frontiers eligible for a later batch instead of silently assigning a score.
    """
    if not response_text:
        return {}
    start = response_text.find("{")
    end = response_text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("batch response contains no JSON object")
    payload = json.loads(response_text[start : end + 1])
    items = payload.get("frontiers")
    if not isinstance(items, list):
        raise ValueError("batch JSON must contain a 'frontiers' list")

    requested_ids = set(requested_ids)
    parsed = {}
    for item in items:
        if not isinstance(item, dict):
            logging.warning("Ignoring non-object batch frontier result: %r", item)
            continue
        try:
            frontier_id = _normalise_frontier_id(item["id"])
            if frontier_id not in requested_ids:
                logging.warning(
                    "Ignoring batch result for unrequested frontier F_%s", frontier_id
                )
                continue
            if frontier_id in parsed:
                logging.warning("Ignoring duplicate batch result for F_%s", frontier_id)
                continue
            parsed[frontier_id] = _result_to_potential_text(item)
        except (KeyError, TypeError, ValueError) as error:
            logging.warning("Ignoring malformed batch frontier result %r: %s", item, error)
    return parsed


def format_batch_content(
    indexed_images: Sequence[Tuple[int, object]], question_text, question_image_path, metadata
):
    """Build one multimodal request containing every new frontier in this step."""
    content = [
        {
            "type": "text",
            "text": (
                "You are a semantic reasoning agent assisting a robot in indoor "
                "navigation. Rate EVERY numbered frontier observation below "
                "independently for the current goal.\n\n"
                "Return ONLY one valid JSON object, with no markdown fences or "
                "additional text, in exactly this schema:\n"
                '{"frontiers":[{"id":0,"semantic_richness":"Low|Medium|High",'
                '"explorability":"Low|Medium|High",'
                '"goal_relevance":"Low|Medium|High",'
                '"potential_score":1.0,"explanation":"2-3 sentences"}]}\n\n'
                "Include every supplied ID exactly once. potential_score must be a "
                "number from 1.0 to 5.0.\n\n"
                "Definitions:\n"
                "- semantic_richness: meaningful objects, structures, or cues visible.\n"
                "- explorability: new accessible regions, paths, doors, corridors, or stairs.\n"
                "- goal_relevance: likelihood that this direction contains or leads to the target.\n"
                "- potential_score: overall exploration value (1.0 very low, 3.0 medium, 5.0 very high)."
            ),
        },
        {"type": "text", "text": f"Goal question: {question_text}"},
        {
            "type": "text",
            "text": (
                f"Task type: {metadata.get('task_type', 'unknown')}\n"
                f"Target class: {metadata.get('class', 'unknown')}"
            ),
        },
    ]

    if question_image_path is not None and os.path.exists(question_image_path):
        try:
            question_image = Image.open(question_image_path)
            with io.BytesIO() as output:
                question_image.save(output, format="PNG")
                question_base64 = base64.b64encode(output.getvalue()).decode("utf-8")
            content.extend(
                [
                    {"type": "text", "text": "Goal image:"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{question_base64}",
                            "detail": "high",
                        },
                    },
                ]
            )
        except Exception as error:
            logging.warning("Unable to load goal image for batch potential scoring: %s", error)
    else:
        content.append({"type": "text", "text": "Goal image: Not provided"})

    for frontier_id, image in indexed_images:
        content.extend(
            [
                {"type": "text", "text": f"Frontier F_{frontier_id}:"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{_encode_image(image)}",
                        "detail": "high",
                    },
                },
            ]
        )
    return content


def get_batch_potential_estimations(
    metadata, indexed_images: Sequence[Tuple[int, object]]
) -> Optional[Dict[int, str]]:
    """Score all newly-created frontiers from one navigation step in one VLM call.

    Returns legacy score text keyed by the *current frontier index*.  A request
    failure returns ``None``; malformed individual items are omitted so they can
    be attempted again in a later step.
    """
    if not indexed_images:
        return {}

    rate_limit_retries = 0
    other_error_retries = 0
    max_rate_limit_retries = 30
    max_other_error_retries = 15
    requested_ids = [frontier_id for frontier_id, _ in indexed_images]
    message_text = [
        {
            "role": "user",
            "content": format_batch_content(
                indexed_images,
                metadata["question"],
                metadata.get("image"),
                metadata,
            ),
        }
    ]

    while True:
        attempt = rate_limit_retries + other_error_retries + 1
        request_start = time.perf_counter()
        try:
            completion = client.chat.completions.create(
                model="gemma3:27b",
                messages=message_text,
                # Keep the legacy potential-estimation sampling setting so the
                # serial-vs-batch ablation changes request packing only.
                temperature=0.7,
                max_tokens=4096,
                top_p=0.95,
                frequency_penalty=0,
                presence_penalty=0,
            )
            record_vlm_response(
                "frontier_potential_batch",
                time.perf_counter() - request_start,
                success=True,
                attempt=attempt,
            )
            response_text = completion.choices[0].message.content
            try:
                return _parse_batch_response(response_text, requested_ids)
            except (json.JSONDecodeError, ValueError, TypeError) as error:
                logging.warning("Unable to parse batch potential response: %s", error)
                logging.debug("Raw batch potential response: %r", response_text)
                return {}
        except openai.RateLimitError as error:
            record_vlm_response(
                "frontier_potential_batch",
                time.perf_counter() - request_start,
                success=False,
                attempt=attempt,
                error_type=type(error).__name__,
            )
            rate_limit_retries += 1
            wait_time = min(60 + (rate_limit_retries * 10), 300)
            logging.warning(
                "Batch potential rate limit (%d); retrying in %ss",
                rate_limit_retries,
                wait_time,
            )
            time.sleep(wait_time)
            if rate_limit_retries >= max_rate_limit_retries:
                logging.warning("Pausing 15 minutes after repeated batch rate limits")
                time.sleep(900)
                rate_limit_retries = 0
        except (openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError) as error:
            record_vlm_response(
                "frontier_potential_batch",
                time.perf_counter() - request_start,
                success=False,
                attempt=attempt,
                error_type=type(error).__name__,
            )
            other_error_retries += 1
            if other_error_retries > max_other_error_retries:
                logging.warning("Batch potential request failed too often: %s", error)
                return None
            wait_time = min(30 + (other_error_retries * 15), 180)
            logging.warning(
                "Batch potential API error (%d); retrying in %ss: %s",
                other_error_retries,
                wait_time,
                error,
            )
            time.sleep(wait_time)
        except openai.BadRequestError as error:
            record_vlm_response(
                "frontier_potential_batch",
                time.perf_counter() - request_start,
                success=False,
                attempt=attempt,
                error_type=type(error).__name__,
            )
            logging.warning("Batch potential request rejected: %s", error)
            return None
        except Exception as error:
            record_vlm_response(
                "frontier_potential_batch",
                time.perf_counter() - request_start,
                success=False,
                attempt=attempt,
                error_type=type(error).__name__,
            )
            other_error_retries += 1
            if other_error_retries > max_other_error_retries:
                logging.warning("Unexpected batch potential failure: %s", error)
                return None
            wait_time = min(30 + (other_error_retries * 15), 180)
            logging.warning(
                "Unexpected batch potential error (%d); retrying in %ss: %s",
                other_error_retries,
                wait_time,
                error,
            )
            time.sleep(wait_time)
