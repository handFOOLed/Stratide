"""Versioned research expressions. Data only: no executable source or external IO."""
from __future__ import annotations

from collections import Counter, deque
from decimal import Decimal as D
import json
import random

import multistock_research as m

require, Error, canonical, sha = m.require, m.Error, m.canonical, m.sha
VERSION = "research-ast-v1"
LIMITS = dict(depth=8, nodes=48, window=60, candidates=8)
UNITS = dict(returns="ratio", volatility="ratio", amount="thousand_CNY", pb="ratio", pe="ratio")


def fields(obj, names):
    require(type(obj) is dict and set(obj) == set(names.split()), "AST_SCHEMA_FIELDS")


def integer(v, lo, hi):
    require(type(v) is int and lo <= v <= hi, "AST_INTEGER_BOUND")


def decimal(v, lo=None, hi=None):
    require(type(v) is str and len(v) <= 40, "AST_DECIMAL_TEXT")
    n = m.number(v)
    require((lo is None or n >= lo) and (hi is None or n <= hi), "AST_DECIMAL_BOUND")
    return n


def validate(ast, position_cap=50):
    fields(ast, "version score filter top_k exposure rebalance_sessions min_hold_sessions")
    require(ast["version"] == VERSION, "AST_VERSION")
    integer(ast["top_k"], 1, position_cap)
    decimal(ast["exposure"], D(0), D(1))
    integer(ast["rebalance_sessions"], 1, 20)
    integer(ast["min_hold_sessions"], 1, 20)
    require(ast["min_hold_sessions"] <= ast["rebalance_sessions"], "AST_HOLDING_CONSTRAINT")
    count = 0

    def node(n, depth=1):
        nonlocal count
        count += 1
        require(depth <= LIMITS["depth"] and count <= LIMITS["nodes"], "AST_COMPLEXITY_LIMIT")
        require(type(n) is dict and type(n.get("op")) is str, "AST_NODE")
        op = n["op"]
        if op == "feature":
            fields(n, "op name window lag unit missing")
            require(n["name"] in UNITS and n["unit"] == UNITS[n["name"]], "AST_FEATURE_UNIT")
            integer(n["window"], 2 if n["name"] == "volatility" else 1, LIMITS["window"])
            require(n["lag"] == 1 and type(n["lag"]) is int, "FUTURE_FEATURE_DENIED")
            require(n["missing"] == "reject_security", "AST_MISSING_POLICY")
            if n["name"] in ("pb", "pe"):
                require(n["window"] == 1, "VALUATION_WINDOW")
            return "number", n["unit"]
        if op in ("negate", "rank"):
            fields(n, "op arg")
            kind, unit = node(n["arg"], depth+1)
            require(kind == "number", "AST_TYPE")
            return "number", "rank_ratio" if op == "rank" else unit
        if op == "blend":
            fields(n, "op terms")
            require(type(n["terms"]) is list and 2 <= len(n["terms"]) <= 4, "AST_BLEND_SIZE")
            units, total = set(), D(0)
            for term in n["terms"]:
                fields(term, "weight arg")
                total += decimal(term["weight"], D(0), D(1))
                kind, unit = node(term["arg"], depth+1)
                require(kind == "number", "AST_TYPE")
                units.add(unit)
            require(total == 1 and len(units) == 1, "AST_BLEND_UNITS_OR_WEIGHTS")
            return "number", units.pop()
        if op == "threshold":
            fields(n, "op arg direction value unit")
            kind, unit = node(n["arg"], depth+1)
            require(kind == "number" and n["unit"] == unit, "AST_THRESHOLD_UNIT")
            require(n["direction"] in ("ge", "le"), "AST_THRESHOLD_DIRECTION")
            decimal(n["value"])
            return "bool", "bool"
        if op in ("and", "or"):
            fields(n, "op args")
            require(type(n["args"]) is list and 2 <= len(n["args"]) <= 4, "AST_LOGIC_SIZE")
            for arg in n["args"]:
                require(node(arg, depth+1)[0] == "bool", "AST_TYPE")
            return "bool", "bool"
        if op == "true":
            fields(n, "op")
            return "bool", "bool"
        raise Error("AST_OPERATOR_DENIED")

    require(node(ast["score"])[0] == "number" and node(ast["filter"])[0] == "bool", "AST_TYPE")
    return sha(canonical(ast))


def unique(pairs):
    out = {}
    for k, v in pairs:
        require(k not in out, "DUPLICATE_JSON_FIELD")
        out[k] = v
    return out


def parse_proposal(raw, expected_source, position_cap):
    """A local equivalent of an Agent result, explicitly distinct from Rust text tasks."""
    require(type(raw) is bytes and len(raw) <= 32768, "PROPOSAL_SIZE")
    p = json.loads(raw, object_pairs_hook=unique,
                   parse_constant=lambda _: require(False, "NONFINITE_JSON"))
    fields(p, "contract source hypothesis ast authority")
    require(p["contract"] == "structured-research-proposal-v1", "STRUCTURED_PROPOSAL_REQUIRED")
    require(p["source"] == expected_source and expected_source["kind"] == "trusted_local_deterministic_v1",
            "PROPOSAL_SOURCE_MISMATCH")
    require(p["authority"] == "RESEARCH_ONLY", "PROPOSAL_AUTHORITY_DENIED")
    require(type(p["hypothesis"]) is str and 1 <= len(p["hypothesis"]) <= 1000, "PROPOSAL_HYPOTHESIS")
    return dict(p, ast_sha=validate(p["ast"], position_cap))


def feature(name, window):
    return dict(op="feature", name=name, window=window, lag=1, unit=UNITS[name], missing="reject_security")


def rank(arg):
    return dict(op="rank", arg=arg)


def threshold(arg, value, unit, direction="ge"):
    return dict(op="threshold", arg=arg, value=value, unit=unit, direction=direction)


def propose(seed, round_number, cap, feedback=None, seen=()):
    """Four grammar families; seed selects bounded windows, never realized winners."""
    if feedback is not None:
        fields(feedback, "contract round_sha window role reduce_exposure evaluated failed_or_negative evidence_allowed_for_next_round selection")
        require(feedback["contract"] == "development-feedback-v1" and feedback["role"] == "development"
                and feedback["evidence_allowed_for_next_round"] == "DEVELOPMENT_ONLY", "NON_DEVELOPMENT_FEEDBACK_DENIED")
    # Provenance hashes bind all source periods. They must not become random-number/selection inputs.
    learning = dict(reduce_exposure=feedback["reduce_exposure"]) if feedback else None
    rng = random.Random(f"{seed}:{round_number}:{sha(canonical(learning))}")
    w = rng.choice([10, 15, 20, 30])
    # Development evidence can shrink prospective exposure; no validation/evaluation inputs.
    reduced = bool(feedback and feedback["reduce_exposure"])
    hypotheses = ["检验已完成收益的延续", "反对延续，检验逆向收益", "检验低波动与流动性交集", "检验收益/低波动组合和流动性替代条件"]
    out, accepted = [], set(seen)
    for i in range(4):
        preferred = 20 if i == 2 else w
        # At most four grammar choices per family; no outcome is evaluated to choose a fallback.
        for window in [preferred]+[v for v in (10,15,20,30) if v != preferred]:
            ret = feature("returns", window)
            vol = feature("volatility", window if i == 2 else 20)
            amount = feature("amount", 5)
            positive, liquid = threshold(ret, "0", "ratio"), threshold(amount, "10000", "thousand_CNY")
            scores = [ret, dict(op="negate", arg=ret), dict(op="negate", arg=vol),
                dict(op="blend", terms=[dict(weight="0.5", arg=rank(ret)),
                                        dict(weight="0.5", arg=rank(dict(op="negate", arg=vol)))])]
            filters = [positive, dict(op="true"), dict(op="and", args=[liquid, threshold(vol, "0.08", "ratio", "le")]),
                       dict(op="or", args=[positive, threshold(rank(amount), "0.7", "rank_ratio")])]
            ast = dict(version=VERSION, score=scores[i], filter=filters[i], top_k=cap,
                       exposure="0.5" if reduced else ("0.8" if i == 3 else "1"),
                       rebalance_sessions=5, min_hold_sessions=5)
            digest = validate(ast, cap)
            if digest not in accepted:
                accepted.add(digest)
                out.append(dict(ast=ast, hypothesis=hypotheses[i], ast_sha=digest))
                break
    return out


class Features(m.Features):
    def __init__(self, config):
        super().__init__(config)
        self.amounts = {}
        self.cache = {}

    def update(self, day, index):
        for row in day["rows"]:
            code = row["ts_code"]
            q = self.amounts.setdefault(code, deque(maxlen=self.lookback+1))
            if self.last_index.get(code, index-1) != index-1:
                q.clear()
            if m.price(row, "close") is None:
                q.clear()
            else:
                q.append(str(row["daily"]["amount"]))
        super().update(day, index)
        self.cache = {}

    def evaluate(self, node, eligible):
        key = canonical(node)
        if key in self.cache:
            return self.cache[key]
        op, result = node["op"], {}
        if op == "feature":
            name, window = node["name"], node["window"]
            for code, prices in eligible.items():
                if name == "returns":
                    value = prices[-1]/prices[-window-1]-1
                elif name == "volatility":
                    rs = [prices[j]/prices[j-1]-1 for j in range(len(prices)-window, len(prices))]
                    avg = sum(rs, D(0))/window
                    value = (sum(((r-avg)**2 for r in rs), D(0))/(window-1)).sqrt()
                elif name == "amount":
                    q = self.amounts[code]
                    if len(q) < window:
                        continue
                    value = sum((D(v) for v in list(q)[-window:]), D(0))/window
                else:
                    basic = self.current[code]["daily_basic"]
                    text = basic.get(name) if basic else None
                    if text is None or D(text) <= 0:
                        continue
                    value = D(text)
                result[code] = value
        elif op in ("negate", "rank"):
            values = self.evaluate(node["arg"], eligible)
            if op == "negate":
                result = {c:-v for c,v in values.items()}
            else:
                ordered = sorted(values, key=lambda c:(values[c], c))
                result = {c:D(i+1)/len(ordered) for i,c in enumerate(ordered)}
        elif op == "blend":
            values = [(D(t["weight"]), self.evaluate(t["arg"], eligible)) for t in node["terms"]]
            common = set.intersection(*(set(v) for _,v in values))
            result = {c:sum((w*v[c] for w,v in values), D(0)) for c in common}
        elif op == "true":
            result = dict.fromkeys(eligible, True)
        elif op == "threshold":
            values = self.evaluate(node["arg"], eligible)
            bound = D(node["value"])
            result = {c:(v >= bound if node["direction"] == "ge" else v <= bound) for c,v in values.items()}
        else:
            values = [self.evaluate(arg, eligible) for arg in node["args"]]
            # Even OR cannot silently substitute a missing prerequisite feature.
            common = set.intersection(*(set(v) for v in values))
            test = all if op == "and" else any
            result = {c:test(v[c] for v in values) for c in common}
        self.cache[key] = result
        return result

    def targets(self, ast, eligible):
        scores = self.evaluate(ast["score"], eligible)
        selected = self.evaluate(ast["filter"], eligible)
        codes = sorted((c for c in scores if selected.get(c, False)), key=lambda c:(-scores[c], c))[:ast["top_k"]]
        target = {c:str(D(w)*D(ast["exposure"])) for c,w in m.weights(codes).items()}
        return target, dict(eligible=len(eligible), missing_features=len(set(eligible)-scores.keys() | (set(eligible)-selected.keys())),
                           selected=len(codes), reason="EMPTY_OR_FILTERED_TO_CASH" if not codes else "RESEARCH_ONLY")


def development_feedback(round_sha, result, windows):
    """Only this projection crosses into the proposal generator; no full result object."""
    names = [w["name"] for w in windows if w["role"] == "development"]
    require(len(names) == 1, "ONE_DEVELOPMENT_SEGMENT_REQUIRED")
    values = result["windows"][names[0]]
    candidate = {k:v for k,v in values.items() if k.startswith("candidate_") and k.endswith("/base")}
    observed = [v for v in candidate.values() if v["total_return"] is not None]
    return dict(contract="development-feedback-v1", round_sha=round_sha, window=names[0],
                role="development", reduce_exposure=bool(observed and any(D(v["max_drawdown"]) < D("-0.2") for v in observed)),
                evaluated=len(observed), failed_or_negative=sum(D(v["total_return"]) <= 0 for v in observed),
                evidence_allowed_for_next_round="DEVELOPMENT_ONLY",
                selection="no_return_maximization_no_holdout_feedback")
