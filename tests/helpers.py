from trail_rating_builder.models import Participant


class FakeRatingProvider:
    provider = "itra"

    def __init__(self, responses):
        self.responses = responses
        self.queries = []

    def find_runner(self, name, count=10):
        self.queries.append(name)
        return self.responses.get(name, [])


def participant(first="Will", last="SMITH", age_group="M35-39"):
    return Participant(
        bib="1086",
        race_result_id="76",
        display_name=f"{last}, {first}",
        first_name=first,
        last_name=last,
        age_group=age_group,
        gender="male" if age_group.startswith("M") else "female",
        club="Bad Boys",
        contest="ULTRA 70",
    )
