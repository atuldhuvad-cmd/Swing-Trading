import sqlite3
from pathlib import Path
c = sqlite3.connect(f"file:{Path(r'D:\\Swing Trading\\data\\swing_trading.db')}?mode=ro", uri=True)
for t in ['fundamental_snapshot','fundamental_metric','candidate_evaluation_run','candidate_criterion_result','risk_reward_result','corporate_action']:
    print('\n====', t)
    print(list(c.execute("SELECT sql FROM sqlite_master WHERE name=?", (t,))))
print('\nall', [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1")])
c.close()
