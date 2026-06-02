"""Auto-generated Kedro pipeline registry. DO NOT EDIT MANUALLY."""
from functools import partial, update_wrapper
from kedro.pipeline import Pipeline, node
from choregraph.library import filter_less_than


def register_pipelines() -> dict[str, Pipeline]:
    """Register the pipelines for this Kedro project."""
    pipeline = Pipeline([
    node(
        func=update_wrapper(partial(filter_less_than, **{'column': 'minimum_nights', 'value': 300.0}), filter_less_than),
        inputs={'df': 'airbnb'},
        outputs='filtered_minimum_nights',
        name='Filter_minimum_nights_less_than_300'
    )
    ])

    return {
        "__default__": pipeline,
        "choregraph": pipeline
    }
