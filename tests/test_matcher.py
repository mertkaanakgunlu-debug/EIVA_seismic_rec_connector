from shotlogfixer.models import EivaRecord, RecorderRecord
from shotlogfixer.matcher import match_records
def e(i,x): return EivaRecord(i,str(i),x,0,[str(i),str(x),'0'])
def r(i,x,y=0): return RecorderRecord(i,str(i),x,y,not (x==-214748.3648 and y==-214748.3648))
def test_alignment():
    out=match_records([e(i,i) for i in range(3)],[r(i,i) for i in range(3)]); assert [x.status for x in out[:3]]==['MATCHED']*3
def test_initial_only():
    out=match_records([e(i,i) for i in range(5)],[r(1,2),r(2,3),r(3,4)]); assert {x.eiva_record.original_ffid for x in out if x.status=='EIVA_ONLY'}=={'0','1'}
def test_invalid(): assert match_records([e(1,0)],[r(1,-214748.3648,-214748.3648)])[0].status=='RECORDER_INVALID'
def test_gap_and_tolerance(): assert match_records([e(1,0),e(2,1.03)],[r(1,1)])[0].status=='MATCHED'
