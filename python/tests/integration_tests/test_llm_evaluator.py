import pytest

from langsmith import Client, evaluate
from langsmith.evaluation.llm_evaluator import (
    CategoricalScoreConfig,
    ContinuousScoreConfig,
    LLMEvaluator,
)


def test_llm_evaluator_init() -> None:
    evaluator = LLMEvaluator(
        prompt_template="Is the response vague? Y/N\n{input}",
        score_config=CategoricalScoreConfig(
            key="vagueness",
            choices=["Y", "N"],
            description="Whether the response is vague. Y for yes, N for no.",
            include_explanation=True,
        ),
    )
    assert evaluator is not None
    assert evaluator.prompt.input_variables == ["input"]
    assert evaluator.score_schema == {
        "title": "vagueness",
        "description": "Whether the response is vague. Y for yes, N for no.",
        "type": "object",
        "properties": {
            "score": {
                "type": "string",
                "enum": ["Y", "N"],
                "description": "The score for the evaluation, one of Y, N.",
            },
            "explanation": {
                "type": "string",
                "description": "The explanation for the score.",
            },
        },
        "required": ["score", "explanation"],
    }

    # Try a continuous score
    evaluator = LLMEvaluator(
        prompt_template="Rate the response from 0 to 1.\n{input}",
        score_config=ContinuousScoreConfig(
            key="rating",
            description="The rating of the response, from 0 to 1.",
            include_explanation=False,
        ),
    )

    assert evaluator is not None
    assert evaluator.prompt.input_variables == ["input"]
    assert evaluator.score_schema == {
        "title": "rating",
        "description": "The rating of the response, from 0 to 1.",
        "type": "object",
        "properties": {
            "score": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "The score for the evaluation, "
                "between 0 and 1, inclusive.",
            },
        },
        "required": ["score"],
    }

    # Test invalid model
    with pytest.raises(ValueError):
        LLMEvaluator(
            prompt_template="Rate the response from 0 to 1.\n{input}",
            score_config=ContinuousScoreConfig(
                key="rating",
                description="The rating of the response, from 0 to 1.",
                include_explanation=False,
            ),
            model_provider="invalid",
        )

    evaluator = LLMEvaluator(
        prompt_template="Rate the response from 0 to 1.\n{input} {output} {expected}",
        score_config=ContinuousScoreConfig(
            key="rating",
            description="The rating of the response, from 0 to 1.",
            include_explanation=False,
        ),
    )
    assert evaluator is not None
    assert set(evaluator.prompt.input_variables) == {"input", "output", "expected"}

    with pytest.raises(ValueError):
        # Test invalid input variable without map_variables
        LLMEvaluator(
            prompt_template="Rate the response from 0 to 1.\n{input} {output} {hello}",
            score_config=ContinuousScoreConfig(
                key="rating",
                description="The rating of the response, from 0 to 1.",
                include_explanation=False,
            ),
        )

    evaluator = LLMEvaluator(
        prompt_template="Rate the response from 0 to 1.\n{input} {output} {hello}",
        score_config=ContinuousScoreConfig(
            key="rating",
            description="The rating of the response, from 0 to 1.",
            include_explanation=False,
        ),
        map_variables=lambda run, example: {"hello": "world"},
    )
    assert evaluator is not None
    assert set(evaluator.prompt.input_variables) == {"input", "output", "hello"}


def test_from_model() -> None:
    from langchain_openai import ChatOpenAI

    evaluator = LLMEvaluator.from_model(
        ChatOpenAI(),
        prompt_template="Rate the response from 0 to 1.\n{input}",
        score_config=ContinuousScoreConfig(
            key="rating",
            description="The rating of the response, from 0 to 1.",
            include_explanation=False,
        ),
    )
    assert evaluator is not None
    assert evaluator.prompt.input_variables == ["input"]
    assert evaluator.score_schema == {
        "title": "rating",
        "description": "The rating of the response, from 0 to 1.",
        "type": "object",
        "properties": {
            "score": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "The score for the evaluation, "
                "between 0 and 1, inclusive.",
            },
        },
        "required": ["score"],
    }


def test_evaluate() -> None:
    client = Client()
    client.clone_public_dataset(
        "https://smith.langchain.com/public/419dcab2-1d66-4b94-8901-0357ead390df/d"
    )
    dataset_name = "Evaluate Examples"

    def predict(inputs: dict) -> dict:
        return {"answer": "Yes"}

    reference_accuracy = LLMEvaluator(
        prompt_template="Is the output accurate with respect to the expected output? "
        "Y/N\nOutput: {output}\nExpected: {expected}",
        score_config=CategoricalScoreConfig(
            key="reference_accuracy",
            choices=["Y", "N"],
            description="Whether the output is accurate with respect to "
            "the expected output.",
            include_explanation=False,
        ),
    )

    accuracy = LLMEvaluator(
        prompt_template=[
            (
                "system",
                "Is the output accurate with respect to the context and "
                "question? Y/N",
            ),
            ("human", "Context: {context}\nQuestion: {question}\nOutput: {output}"),
        ],
        score_config=CategoricalScoreConfig(
            key="accuracy",
            choices=["Y", "N"],
            description="Whether the output is accurate with respect to "
            "the context and question.",
            include_explanation=True,
        ),
        map_variables=lambda run, example: {
            "context": example.inputs.get("context", "") if example else "",
            "question": example.inputs.get("question", "") if example else "",
            "output": run.outputs.get("output", "") if run.outputs else "",
        },
        model_provider="anthropic",
        model_name="claude-3-haiku-20240307",
    )

    results = evaluate(
        predict,
        data=dataset_name,
        evaluators=[reference_accuracy, accuracy],
    )
    results.wait()
