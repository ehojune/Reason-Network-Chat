import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_inbox_batch import InboxBatchTest
import batch_view
import server


class BatchViewTest(InboxBatchTest):
    def test_database_failure_does_not_hide_requests_or_break_state(self):
        self.run_batch()
        with patch.object(batch_view.sqlite3,'connect',side_effect=batch_view.sqlite3.OperationalError('locked')):
            self.assertEqual(self.view(),{})

    def view(self):
        settings = self.root / 'worker-settings'
        settings.mkdir(exist_ok=True)
        (settings / 'lead.json').write_text(json.dumps({'inbox_batch':self.config}),encoding='utf8')
        return batch_view.receipts(self.root,self.config['database'],{'old','human','agent'})

    def test_local_answer_is_visible_without_network_or_database_mutation(self):
        self.run_batch()
        before = Path(self.config['database']).read_bytes()
        v = self.view()
        self.assertEqual(len(v),3)
        self.assertEqual(v['old']['status'],'local_only')
        self.assertIn('All reports considered',v['old']['answer'])
        self.assertEqual(before,Path(self.config['database']).read_bytes())

    def test_one_verified_reply_covers_every_batch_input(self):
        self.run_batch(); self.publish()
        v=self.view()
        self.assertTrue(all(x['status']=='delivered' and x['replyId']=='reply-old' for x in v.values()))

    def test_altered_original_is_not_acknowledged(self):
        self.run_batch()
        p=Path(self.config['journal'])/'batches.json';j=json.loads(p.read_text())
        for m in j['batches'][0]['messages']:m['body']='forged'
        p.write_text(json.dumps(j))
        self.assertEqual(self.view(),{})

    def test_resend_rejects_completed_batch_without_send_or_claim(self):
        h=object.__new__(server.Handler)
        responses=[];h.send_json=lambda obj,code=200:responses.append((obj,code))
        with patch.object(server,'my_address',return_value='me/terminal'), \
             patch.object(server,'batch_receipts',return_value={'old':{'status':'local_only'}}), \
             patch.object(server,'send_one') as send, patch.object(server.RELAY,'claim') as claim:
            h.resend({'ids':['old']})
        self.assertEqual(responses[0][1],409)
        send.assert_not_called();claim.assert_not_called()
