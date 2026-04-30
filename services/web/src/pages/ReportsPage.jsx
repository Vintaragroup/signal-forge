import { useEffect, useState } from "react";
import { api } from "../api.js";
import ReportCard from "../components/ReportCard.jsx";

export default function ReportsPage() {
  const [reports, setReports] = useState([]);

  useEffect(() => {
    api.reports().then((data) => setReports(data.items || []));
  }, []);

  return (
    <div className="grid gap-5 xl:grid-cols-2">
      {reports.map((report) => (
        <ReportCard key={report.path} report={report} />
      ))}
    </div>
  );
}
