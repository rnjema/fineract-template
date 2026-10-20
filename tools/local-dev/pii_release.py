# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership. The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.

"""Known-fixture leakage smoke check. This is not an anonymization implementation or certification."""
import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation
from datetime import date
import json
from pathlib import Path
from pii_fixture import normalized


def objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        yield format(value, 'f') if isinstance(value, Decimal) else str(value)
    elif isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            if normalized(str(key)) in {'dateofbirth', 'birthdate', 'dob'} and isinstance(child, list) and len(child) == 3:
                try:
                    yield date(*child).isoformat()
                except (TypeError, ValueError):
                    pass
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)


def evaluate(release, answer_key, linkage_map=None):
    linkage_map = linkage_map or {}
    texts = list(strings(release))
    # Delimit individual strings so the scanner does not invent identifiers spanning fields.
    canonical_texts = [normalized(text) for text in texts]
    unique = {(o['type'], normalized(o.get('canonical') or o['value'])) for o in answer_key['occurrences']}
    found = Counter()
    for kind, value in unique:
        if value and any(value in text for text in canonical_texts):
            found[kind] += 1
    by_external = {}
    for obj in objects(release):
        external = obj.get('externalId') or obj.get('external_id')
        if external:
            by_external[str(external)] = obj
    matched, changed, unjoinable = 0, 0, 0
    for control in answer_key.get('financial_controls', []):
        obj = by_external.get(linkage_map.get(control['external_id'], control['external_id']))
        if obj is None:
            unjoinable += 1
            continue
        try:
            if Decimal(str(obj.get('principal'))) == Decimal(control['principal']):
                matched += 1
            else:
                changed += 1
        except (InvalidOperation, TypeError):
            changed += 1
    return {'known_planted_identifiers_absent': not bool(found), 'unique_identifiers_checked': len(unique),
            'unique_identifiers_found': sum(found.values()), 'found_by_type': dict(found),
            'financial_controls_matched': matched,
            'financial_controls_changed': changed, 'financial_controls_unjoinable': unjoinable,
            'linkage_consistency': 'not evaluated', 'unknown_pii_detection': 'not evaluated',
            'quasi_identifier_risk': 'not evaluated', 'scanner_false_positive_rate': 'not evaluated',
            'clean_text_false_removals': 'not evaluated',
            'privacy_certified': False,
            'scope': 'Known planted identifiers in supplied JSON; normalized comparison; no policy or production privacy certification'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--release', type=Path, required=True)
    parser.add_argument('--answer-key', type=Path, default=Path(__file__).parent / '.runtime/pii-testbed/answer-key.json')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--linkage-map', type=Path, help='Restricted JSON mapping of fixture loan external IDs to released tokens')
    args = parser.parse_args()
    result = evaluate(json.loads(args.release.read_text(encoding='utf-8'), parse_float=Decimal),
                      json.loads(args.answer_key.read_text(encoding='utf-8')),
                      json.loads(args.linkage_map.read_text(encoding='utf-8')) if args.linkage_map else None)
    if args.report:
        args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
