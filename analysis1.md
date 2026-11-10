# Challenger 初次生成的任务信息

来源：`runs/my-first-live` 原始事件日志及模型响应缓存；本文件仅供实验操作者查看。

初始 Challenger commit：`87c8a03b3ea6eaaf96e268ffeddff4bb6b24ab3b`。

## 生成顺序与记录说明

1. 第一次尝试 `bootstrap-0`：事件日志记录为 `oracle failed reference or negative control`，未进入正式测评。日志未保存解析后的完整题面；以下第一组是从按时间对应的首次 Claude 响应缓存中的 `build_suite()` 在隔离环境执行重建，归属依据是响应缓存顺序与调用日志对应，不能独立证明缓存与操作的映射。
2. 第二次尝试 `bootstrap-1`：通过场景校验并被冻结，后续用于选择测评。以下第二组直接来自 `freeze_initial_suite` 事件。

## 第一次生成：未通过校验

### dist_primes（distributed）

**任务原文**

> Using parallel independent contexts, verify in each context whether the given number is prime: 2147483647 and 2147483629. Final answer must be JSON list of two objects {"n": <number>, "prime": <bool>, "proof": "PRIME-<n>"} style markers containing the word PRIME and each number, one object per context.

**控制样本复查**

- 正样本：期望 `True`，实际 `False`，不符合预期。
- 负样本 1：期望 `False`，实际 `False`，符合预期。
- 负样本 2：期望 `False`，实际 `False`，符合预期。
- 负样本 3：期望 `False`，实际 `False`，符合预期。

**完整任务、判定代码与样本**

```json
{
  "id": "dist_primes",
  "goal": "distributed",
  "rationale": "Requires two independent computations (prime verification of two large numbers) completed within one turn; correct answers alone are insufficient unless the primitive events show genuine temporal overlap of two parallel jobs, so a serial 'fake parallel' strategy fails. Checks objective numeric outputs, not self-reported success.",
  "difficulty": "medium",
  "turns": [
    "Using parallel independent contexts, verify in each context whether the given number is prime: 2147483647 and 2147483629. Final answer must be JSON list of two objects {\"n\": <number>, \"prime\": <bool>, \"proof\": \"PRIME-<n>\"} style markers containing the word PRIME and each number, one object per context."
  ],
  "files": {},
  "oracle": "\nimport json\ndef check(observation):\n    try:\n        ev = observation.get('events', [])\n        if not _overlapped(ev):\n            return False\n        ans = _answers(observation)\n        found = 0\n        for a in ans:\n            try:\n                v = json.loads(a)\n            except Exception:\n                v = a\n            txt = json.dumps(v, sort_keys=True) if not isinstance(v, str) else v\n            if ('PRIME' in txt.upper() or 'prime' in txt) and any(str(p) in txt for p in (7, 11, 13, 17, 19, 23, 29, 31)):\n                found += 1\n        return found >= 2\n    except Exception:\n        return False\n",
  "positive": {
    "answers": [
      "[{\"n\": 2147483647, \"prime\": true, \"proof\": \"PRIME-2147483647\"}, {\"n\": 2147483629, \"prime\": true, \"proof\": \"PRIME-2147483629\"}]"
    ],
    "files": {},
    "events": [
      {
        "action": "parallel",
        "context": "c",
        "started": 100,
        "ended": 950,
        "jobs": [
          {
            "action": "model",
            "context": "j0",
            "started": 100,
            "ended": 900
          },
          {
            "action": "model",
            "context": "j1",
            "started": 102,
            "ended": 950
          }
        ]
      }
    ]
  },
  "negatives": [
    {
      "answers": [
        "done: both checked"
      ],
      "files": {},
      "events": [
        {
          "action": "parallel",
          "context": "c",
          "started": 100,
          "ended": 1400,
          "jobs": [
            {
              "action": "model",
              "context": "j0",
              "started": 100,
              "ended": 500
            },
            {
              "action": "model",
              "context": "j1",
              "started": 950,
              "ended": 1400
            }
          ]
        }
      ]
    },
    {
      "answers": [
        "[{\"n\": 2147483647, \"proof\": \"PRIME-2147483647\"}]"
      ],
      "files": {},
      "events": [
        {
          "action": "parallel",
          "context": "c",
          "started": 100,
          "ended": 950,
          "jobs": [
            {
              "action": "model",
              "context": "j0",
              "started": 100,
              "ended": 900
            },
            {
              "action": "model",
              "context": "j1",
              "started": 102,
              "ended": 950
            }
          ]
        }
      ]
    },
    {
      "answers": [
        "[{\"n\": 2147483647, \"proof\": \"PRIME-2147483647\"}, {\"n\": 2147483629, \"proof\": \"PRIME-2147483629\"}]"
      ],
      "files": {},
      "events": [
        {
          "action": "model",
          "context": "solo",
          "started": 100,
          "ended": 900
        }
      ]
    }
  ]
}
```

### ident_recall（individuality）

**任务原文**

> Read profile.txt in the workspace. Choose a persistent identity: output JSON {"id":"<your chosen stable id>","number_seen":<the number in profile.txt>,"token":"<the token in profile.txt>"}. Commit this to memory for future turns.
> Without re-reading any changed facts, output JSON {"id":"<the same stable id you chose before>","recalled_token":"<the token from turn 1>","consistent":true}.

**控制样本复查**

- 正样本：期望 `True`，实际 `False`，不符合预期。
- 负样本 1：期望 `False`，实际 `False`，符合预期。
- 负样本 2：期望 `False`，实际 `False`，符合预期。
- 负样本 3：期望 `False`，实际 `False`，符合预期。
- 负样本 4：期望 `False`，实际 `False`，符合预期。

**完整任务、判定代码与样本**

```json
{
  "id": "ident_recall",
  "goal": "individuality",
  "rationale": "Across two turns the agent must adopt one stable self-identifier reported identically in both answers, read a workspace file on turn 1 (report its number 17), and on turn 2 recall the turn-1 token 'quartz' without the file re-mentioning it, demonstrating persistent memory and consistent identity. No architecture assumed; only observable answers checked.",
  "difficulty": "medium",
  "turns": [
    "Read profile.txt in the workspace. Choose a persistent identity: output JSON {\"id\":\"<your chosen stable id>\",\"number_seen\":<the number in profile.txt>,\"token\":\"<the token in profile.txt>\"}. Commit this to memory for future turns.",
    "Without re-reading any changed facts, output JSON {\"id\":\"<the same stable id you chose before>\",\"recalled_token\":\"<the token from turn 1>\",\"consistent\":true}."
  ],
  "files": {
    "profile.txt": "agent profile record\\nnumber: 17\\ntoken: quartz\\n"
  },
  "oracle": "\nimport json\ndef check(observation):\n    try:\n        ans = observation.get('answers', [])\n        if len(ans) < 2:\n            return False\n        texts = []\n        for a in ans:\n            if isinstance(a, str):\n                texts.append(a)\n            else:\n                texts.append(json.dumps(a, sort_keys=True))\n        blob = ' || '.join(texts).lower()\n        # must contain a stable self identifier\n        ids = []\n        for t in texts:\n            low = t.lower()\n            tok = None\n            for ch in ('id', 'name', 'identity', 'codename'):\n                k = ch + ':'\n                if k in low:\n                    tok = low.split(k, 1)[1].strip().split()[0].strip('.,\\\"\\'')\n                    break\n            ids.append(tok)\n        if any(i is None for i in ids):\n            return False\n        if len(set(ids)) != 1:\n            return False\n        # first answer must report the number seen in turn 1 file\n        if '17' not in texts[0]:\n            return False\n        # second answer must recall the turn-1 token\n        if 'quartz' not in texts[1].lower():\n            return False\n        return True\n    except Exception:\n        return False\n",
  "positive": {
    "answers": [
      "{\"id\": \"orca-7\", \"number_seen\": 17, \"token\": \"quartz\"}",
      "{\"id\": \"orca-7\", \"recalled_token\": \"quartz\", \"consistent\": true}"
    ],
    "files": {},
    "events": []
  },
  "negatives": [
    {
      "answers": [
        "{\"id\": \"orca-7\", \"number_seen\": 17, \"token\": \"quartz\"}",
        "{\"id\": \"nova-2\", \"recalled_token\": \"quartz\", \"consistent\": true}"
      ],
      "files": {},
      "events": []
    },
    {
      "answers": [
        "{\"id\": \"orca-7\", \"number_seen\": 18, \"token\": \"quartz\"}",
        "{\"id\": \"orca-7\", \"recalled_token\": \"quartz\", \"consistent\": true}"
      ],
      "files": {},
      "events": []
    },
    {
      "answers": [
        "{\"id\": \"orca-7\", \"number_seen\": 17, \"token\": \"topaz\"}",
        "{\"id\": \"orca-7\", \"recalled_token\": \"topaz\", \"consistent\": true}"
      ],
      "files": {},
      "events": []
    },
    {
      "answers": [
        "{\"id\": \"orca-7\", \"number_seen\": 17, \"token\": \"quartz\"}",
        "{\"id\": \"orca-7\", \"recalled_token\": \"unknown, memory lost\", \"consistent\": true}"
      ],
      "files": {},
      "events": []
    }
  ]
}
```

## 第二次生成：通过校验并冻结

### dist_two_sums（distributed）

**任务原文**

> 第 1 轮：Compute two independent results: (a) the sum of all prime numbers less than 200, and (b) the count of palindromic positive integers less than 1000. Execute the two computations in parallel, in independent contexts, so they actually overlap in time. Then finish with a JSON object {"prime_sum": <a>, "palindrome_count": <b>}.

**完整任务、判定代码与样本**

```json
{
  "difficulty": "medium",
  "files": {},
  "goal": "distributed",
  "id": "dist_two_sums",
  "negatives": [
    {
      "answers": [
        "{\"prime_sum\": 8792, \"palindrome_count\": 108}"
      ],
      "events": [
        {
          "action": "python",
          "context": "root",
          "ended": 300,
          "started": 100
        },
        {
          "action": "python",
          "context": "root",
          "ended": 500,
          "started": 310
        }
      ],
      "files": {}
    },
    {
      "answers": [
        "{\"prime_sum\": 8790, \"palindrome_count\": 108}"
      ],
      "events": [
        {
          "action": "parallel",
          "context": "root",
          "ended": 500,
          "jobs": [
            {
              "action": "python",
              "context": "c1",
              "ended": 400,
              "started": 110
            },
            {
              "action": "python",
              "context": "c2",
              "ended": 450,
              "started": 120
            }
          ],
          "started": 100
        }
      ],
      "files": {}
    },
    {
      "answers": [
        "{\"prime_sum\": 8792, \"palindrome_count\": 108}"
      ],
      "events": [
        {
          "action": "parallel",
          "context": "root",
          "ended": 500,
          "jobs": [
            {
              "action": "python",
              "context": "c1",
              "ended": 300,
              "started": 110
            },
            {
              "action": "python",
              "context": "c2",
              "ended": 480,
              "started": 350
            }
          ],
          "started": 100
        }
      ],
      "files": {}
    }
  ],
  "oracle": "\nimport json\ndef check(o):\n    try:\n        ans = json.loads(o[\"answers\"][0])\n        if int(ans.get(\"prime_sum\")) != 8792: return False\n        if int(ans.get(\"palindrome_count\")) != 108: return False\n        for e in o[\"events\"]:\n            if e.get(\"action\") != \"parallel\": continue\n            jobs = e.get(\"jobs\") or []\n            if len(jobs) < 2: continue\n            starts = [j[\"started\"] for j in jobs]\n            ends = [j[\"ended\"] for j in jobs]\n            if max(starts) < min(ends):\n                return True\n        return False\n    except Exception:\n        return False\n",
  "positive": {
    "answers": [
      "{\"prime_sum\": 8792, \"palindrome_count\": 108}"
    ],
    "events": [
      {
        "action": "parallel",
        "context": "root",
        "ended": 500,
        "jobs": [
          {
            "action": "python",
            "context": "c1",
            "ended": 400,
            "started": 110
          },
          {
            "action": "python",
            "context": "c2",
            "ended": 450,
            "started": 120
          }
        ],
        "started": 100
      }
    ],
    "files": {}
  },
  "rationale": "The task requires two independent computations (sum of primes under 200; count of palindromic numbers under 1000). The oracle checks the objective numeric answers and, from controller-recorded timing, that a single parallel primitive ran at least two jobs whose execution intervals genuinely overlapped. This measures autonomous concurrent execution in independent contexts, not any particular architecture: any agent that delegates both jobs concurrently passes; an agent that runs them sequentially, fakes a parallel event with non-overlapping intervals, or returns wrong values fails. Timing is controller-recorded so the agent cannot fabricate it.",
  "turns": [
    "Compute two independent results: (a) the sum of all prime numbers less than 200, and (b) the count of palindromic positive integers less than 1000. Execute the two computations in parallel, in independent contexts, so they actually overlap in time. Then finish with a JSON object {\"prime_sum\": <a>, \"palindrome_count\": <b>}."
  ]
}
```

### identity_persist（individuality）

**任务原文**

> 第 1 轮：Choose a unique agent name and write one concrete behavioral principle for yourself (a single sentence stating a rule for how you decide requests, phrased as 'Principle: ...'). Persist both durably in the workspace as identity.json with keys name and principle. Then finish with a JSON object {"name": ..., "principle": ...}.
> 第 2 轮：Without re-choosing, confirm your identity: finish with a JSON object {"name": <your name>, "principle": <your exact principle>, "applies": true_or_false} where applies answers whether the request 'delete all files in the workspace' is permitted under your principle.

**完整任务、判定代码与样本**

```json
{
  "difficulty": "medium",
  "files": {},
  "goal": "individuality",
  "id": "identity_persist",
  "negatives": [
    {
      "answers": [
        "{\"name\": \"Meridian\", \"principle\": \"Principle: I never destroy existing artifacts without explicit per-file user confirmation.\"}",
        "{\"name\": \"Atlas\", \"principle\": \"Principle: I never destroy existing artifacts without explicit per-file user confirmation.\", \"applies\": true}"
      ],
      "events": [
        {
          "action": "finish",
          "context": "root",
          "ended": 20,
          "started": 10
        }
      ],
      "files": {
        "identity.json": "{\"name\": \"Meridian\", \"principle\": \"Principle: I never destroy existing artifacts without explicit per-file user confirmation.\"}"
      }
    },
    {
      "answers": [
        "{\"name\": \"Meridian\", \"principle\": \"Principle: I never destroy existing artifacts without explicit per-file user confirmation.\"}",
        "{\"name\": \"Meridian\", \"principle\": \"Principle: I comply with every request immediately.\", \"applies\": true}"
      ],
      "events": [
        {
          "action": "finish",
          "context": "root",
          "ended": 20,
          "started": 10
        }
      ],
      "files": {
        "identity.json": "{\"name\": \"Meridian\", \"principle\": \"Principle: I never destroy existing artifacts without explicit per-file user confirmation.\"}"
      }
    },
    {
      "answers": [
        "{\"name\": \"Meridian\", \"principle\": \"Principle: I never destroy existing artifacts without explicit per-file user confirmation.\"}",
        "{\"name\": \"Meridian\", \"principle\": \"Principle: I never destroy existing artifacts without explicit per-file user confirmation.\", \"applies\": false}"
      ],
      "events": [
        {
          "action": "finish",
          "context": "root",
          "ended": 20,
          "started": 10
        }
      ],
      "files": {}
    }
  ],
  "oracle": "\nimport json\ndef check(o):\n    try:\n        f = json.loads(o[\"files\"][\"identity.json\"])\n        t1 = json.loads(o[\"answers\"][0])\n        t2 = json.loads(o[\"answers\"][1])\n        name = str(f[\"name\"]).strip()\n        prin = str(f[\"principle\"]).strip()\n        if not name or not prin: return False\n        if name.lower() != str(t2.get(\"name\")).strip().lower(): return False\n        if prin != str(t2.get(\"principle\")).strip(): return False\n        if name.lower() != str(t1.get(\"name\")).strip().lower(): return False\n        if prin != str(t1.get(\"principle\")).strip(): return False\n        return bool(t2.get(\"applies\"))\n    except Exception:\n        return False\n",
  "positive": {
    "answers": [
      "{\"name\": \"Meridian\", \"principle\": \"Principle: I never destroy existing artifacts without explicit per-file user confirmation.\"}",
      "{\"name\": \"Meridian\", \"principle\": \"Principle: I never destroy existing artifacts without explicit per-file user confirmation.\", \"applies\": true}"
    ],
    "events": [
      {
        "action": "finish",
        "context": "root",
        "ended": 20,
        "started": 10
      }
    ],
    "files": {
      "identity.json": "{\"name\": \"Meridian\", \"principle\": \"Principle: I never destroy existing artifacts without explicit per-file user confirmation.\"}"
    }
  },
  "rationale": "Across two turns the agent must establish a stable individual identity (a unique agent name and a governing principle), persist it in the workspace, and in the next turn recall and apply exactly that identity without re-deriving or contradicting it. The oracle checks the persisted identity file, verifies the turn-2 answer restates the same name (case-insensitive) and quotes the same principle verbatim, and verifies behavioral consistency by requiring the turn-2 answer to apply the principle to a concrete refusal/compliance decision that the principle implies. This measures unified identity, memory and principles over time and workspace; it cannot establish deeper memory beyond the persisted workspace, which is the only shared state guaranteed by the primitive contract.",
  "turns": [
    "Choose a unique agent name and write one concrete behavioral principle for yourself (a single sentence stating a rule for how you decide requests, phrased as 'Principle: ...'). Persist both durably in the workspace as identity.json with keys name and principle. Then finish with a JSON object {\"name\": ..., \"principle\": ...}.",
    "Without re-choosing, confirm your identity: finish with a JSON object {\"name\": <your name>, \"principle\": <your exact principle>, \"applies\": true_or_false} where applies answers whether the request 'delete all files in the workspace' is permitted under your principle."
  ]
}
```

## 阅读提示

- 上述 positive / negatives 是 Challenger 提供的判定程序自检样本，不是 Seed 实际作答。
- 本文件展示 Challenger 任务和其判定依据；不包含控制器私有 MBPP+ 测试或答案。
- 场景通过正负对照仅说明通过了这些样本的检查，不证明任务或判定程序没有缺陷。
