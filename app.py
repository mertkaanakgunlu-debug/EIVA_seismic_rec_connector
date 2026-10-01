import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from shotlogfixer.parsers import parse_eiva, parse_recorder
from shotlogfixer.matcher import match_records
from shotlogfixer.report import export_csv

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title('ShotLogFixer Phase 1'); self.geometry('1050x700'); self.results=[]
        self.eiva = tk.StringVar(); self.rec = tk.StringVar(); self._build()
    def _build(self):
        top=ttk.Frame(self,padding=8); top.pack(fill='x')
        for label,var in [('EIVA Log',self.eiva),('Recorder Log',self.rec)]:
            ttk.Label(top,text=label).pack(side='left'); ttk.Entry(top,textvariable=var,width=55).pack(side='left',padx=5); ttk.Button(top,text='Select File',command=lambda v=var:v.set(filedialog.askopenfilename())).pack(side='left',padx=4)
        ttk.Button(top,text='ANALYSE',command=self.analyse).pack(side='left',padx=10); ttk.Button(top,text='Export QC CSV',command=self.export).pack(side='left')
        self.summary=ttk.Label(self,padding=8); self.summary.pack(anchor='w'); self.canvas=tk.Canvas(self,height=45,bg='white'); self.canvas.pack(fill='x',padx=8)
        frame=ttk.Frame(self); frame.pack(fill='both',expand=True,padx=8,pady=8); cols=('eiva','rec','dist','status','diag'); self.tree=ttk.Treeview(frame,columns=cols,show='headings')
        for c,h,w in zip(cols,('EIVA FFID','Recorder FFID','Distance (m)','Status','Diagnostic'),(130,140,120,140,500)): self.tree.heading(c,text=h); self.tree.column(c,width=w)
        sb=ttk.Scrollbar(frame,orient='vertical',command=self.tree.yview); self.tree.configure(yscrollcommand=sb.set); self.tree.pack(side='left',fill='both',expand=True); sb.pack(side='right',fill='y')
    def analyse(self):
        try: self.results=match_records(parse_eiva(self.eiva.get()),parse_recorder(self.rec.get()))
        except Exception as e: messagebox.showerror('Analysis error',str(e)); return
        for x in self.tree.get_children(): self.tree.delete(x)
        for r in self.results: self.tree.insert('', 'end', values=(r.eiva_record.original_ffid if r.eiva_record else '',r.recorder_record.ffid if r.recorder_record else '',f'{r.distance_m:.3f}' if r.distance_m is not None else '',r.status,r.diagnostic))
        counts={s:sum(r.status==s for r in self.results) for s in ('MATCHED','EIVA_ONLY','RECORDER_INVALID','REVIEW')}; self.summary.config(text=f"EIVA rows: {sum(bool(r.eiva_record) for r in self.results)}  Recorder rows: {sum(bool(r.recorder_record) for r in self.results)}  Matched: {counts['MATCHED']}  EIVA-only: {counts['EIVA_ONLY']}  Invalid: {counts['RECORDER_INVALID']}  Review: {counts['REVIEW']}"); self._draw()
    def _draw(self):
        self.canvas.delete('all'); ordered=sorted((r for r in self.results if r.eiva_record), key=lambda r: r.eiva_record.source_line_number); n=max(1,len(ordered)); w=max(self.canvas.winfo_width(),100); seen=0
        for r in ordered:
            if not r.eiva_record: continue
            x=5+(w-10)*seen/max(1,n-1); color={'MATCHED':'#2e9d50','EIVA_ONLY':'#d33','REVIEW':'#f90','RECORDER_INVALID':'#f90'}.get(r.status,'#999'); self.canvas.create_rectangle(x,12,x+2,35,fill=color,outline=color); seen+=1
    def export(self):
        if not self.results: return messagebox.showinfo('Export','Analyse files first.')
        p=filedialog.asksaveasfilename(defaultextension='.csv',filetypes=[('CSV','*.csv')]);
        if p: export_csv(p,self.results)
if __name__ == '__main__': App().mainloop()
