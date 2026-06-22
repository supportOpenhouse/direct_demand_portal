import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "./components/Toast";
import { VisitPlanner } from "./features/VisitPlanner";
import "./styles/app.css";

const qc = new QueryClient();
const mk = (id:number,name:string,society:string,locality:string,city:string,lacs:number,cfg:string)=>(
  {id,name,society,locality,city,configuration:cfg,area_sqft:1200,price_text:null,price_lacs:lacs,status:"Ready",image_url:null,lat:28.4+id*0.01,lng:77.0+id*0.01,raw:{home_id:String(id)}});
qc.setQueryData(["inventory"], { status:"ok", last_synced_at:null, detail:null, items:[
  mk(1,"M - 1502, ROF Aalayas","ROF Aalayas","Sector 102","Gurgaon",78,"3 BHK"),
  mk(2,"G - 408, Suncity Avenue 102","Suncity Avenue 102","Sector 102","Gurgaon",77,"2 BHK"),
  mk(3,"T4 - 3504, Hero Homes","Hero Homes","Sector 104","Gurgaon",189,"3 BHK"),
  mk(4,"B9 - 1502, Experion Heartsong","Experion The Heartsong","Sector 108","Gurgaon",203,"3 BHK + Servant"),
  mk(5,"RG Residency 12A","RG Residency","Sector 120","Noida",119,"2 BHK"),
  mk(6,"Mahagun Manorial","Mahagun Manorial","Sector 128","Noida",350,"4 BHK"),
]});
qc.setQueryData(["assignees"], { items:[{name:"Rahul Singh",email:"rahul@openhouse.in"},{name:"Saransh",email:"s@openhouse.in"}] });

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><QueryClientProvider client={qc}><ToastProvider>
    <VisitPlanner leadId="x" leadName="TEST Meta Lead" leadCity="Gurgaon" onClose={()=>{}} />
  </ToastProvider></QueryClientProvider></React.StrictMode>
);
