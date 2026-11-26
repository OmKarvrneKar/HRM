import React, { useState, useEffect } from 'react';
import { DollarSign, FileText, Download, CheckCircle, AlertCircle, Building } from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { payrollApi } from '../../services/api/payrollApi';
import StatCard from '../../components/common/StatCard';
import EmptyState from '../../components/common/EmptyState';
import Badge from '../../components/common/Badge';

export const PayrollCenter = () => {
  const { user } = useAuth();
  const [salaryData, setSalaryData] = useState(null);
  const [slips, setSlips] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchSalary = async () => {
      try {
        setLoading(true);
        const data = await payrollApi.getUserSalary(
          user?.employee_id || user?.emp_id || 'AS-1001'
        );
        const sal = data?.salary || data;
        setSalaryData(sal);
        setSlips(data?.slips || sal?.slips || []);
      } catch (e) {
        console.warn('Salary fetch notice:', e);
      } finally {
        setLoading(false);
      }
    };
    if (user) fetchSalary();
  }, [user]);

  const isConfigured = Boolean(
    salaryData &&
    salaryData.configured !== false &&
    (salaryData.basic || salaryData.basic_salary || salaryData.ctc_annual || salaryData.monthly_gross)
  );

  const basic = isConfigured ? (salaryData?.basic || salaryData?.basic_salary || salaryData?.structure?.basic || 0) : 0;
  const hra = isConfigured ? (salaryData?.hra || salaryData?.structure?.hra || 0) : 0;
  const special = isConfigured ? (salaryData?.special_allowance || salaryData?.structure?.special_allowance || 0) : 0;
  const gross = isConfigured ? (salaryData?.monthly_gross || (basic + hra + special)) : 0;
  const pf = isConfigured ? (salaryData?.pf || salaryData?.pf_deduction || salaryData?.structure?.pf || 0) : 0;
  const pt = isConfigured ? (salaryData?.pt || salaryData?.professional_tax || salaryData?.structure?.pt || 0) : 0;
  const deductions = isConfigured ? (salaryData?.total_deductions || (pf + pt)) : 0;
  const netSalary = isConfigured ? (salaryData?.net_salary || (gross - deductions)) : 0;

  const handlePrintSlip = (month) => {
    window.print();
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Payroll, Compensation & Payslips
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Transparent breakdown of salary components, statutory deductions (PF, PT), and monthly payslips.
          </p>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          title="Monthly Net Pay"
          value={isConfigured ? `₹${netSalary.toLocaleString('en-IN')}` : '—'}
          subtitle={isConfigured ? 'Direct deposit to registered bank account' : 'Salary structure not configured'}
          icon={DollarSign}
          color={isConfigured ? 'green' : 'slate'}
        />
        <StatCard
          title="Gross Monthly CTC"
          value={isConfigured ? `₹${gross.toLocaleString('en-IN')}` : '—'}
          subtitle={isConfigured ? 'Fixed base before deductions' : 'Awaiting HR stipend setup'}
          icon={Building}
          color={isConfigured ? 'blue' : 'slate'}
        />
        <StatCard
          title="Statutory Deductions"
          value={isConfigured ? `₹${deductions.toLocaleString('en-IN')}` : '—'}
          subtitle={isConfigured ? 'Provident Fund (PF) + Professional Tax (PT)' : 'No deduction schedule'}
          icon={FileText}
          color={isConfigured ? 'purple' : 'slate'}
        />
      </div>

      {/* Salary Structure Section */}
      {!isConfigured ? (
        <div className="card">
          <EmptyState
            icon={DollarSign}
            title="Salary Structure Not Configured"
            description="No official salary, stipend, or compensation structure has been assigned to your employee account in the database. Please contact HR or Payroll administration."
          />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="card">
            <h2 className="text-base font-bold text-slate-900 mb-4 flex items-center gap-2">
              <DollarSign className="w-4 h-4 text-emerald-600" />
              Earnings Breakdown
            </h2>

            <div className="space-y-3 text-xs">
              <div className="flex justify-between py-2 border-b border-slate-100">
                <span className="text-slate-600">Basic Salary</span>
                <span className="font-mono font-bold text-slate-800">
                  ₹{basic.toLocaleString('en-IN')}
                </span>
              </div>
              <div className="flex justify-between py-2 border-b border-slate-100">
                <span className="text-slate-600">House Rent Allowance (HRA)</span>
                <span className="font-mono font-bold text-slate-800">
                  ₹{hra.toLocaleString('en-IN')}
                </span>
              </div>
              <div className="flex justify-between py-2 border-b border-slate-100">
                <span className="text-slate-600">Special Enterprise Allowance</span>
                <span className="font-mono font-bold text-slate-800">
                  ₹{special.toLocaleString('en-IN')}
                </span>
              </div>
              <div className="flex justify-between pt-2 text-sm font-bold text-emerald-700">
                <span>Gross Earnings</span>
                <span className="font-mono">₹{gross.toLocaleString('en-IN')}</span>
              </div>
            </div>
          </div>

          <div className="card">
            <h2 className="text-base font-bold text-slate-900 mb-4 flex items-center gap-2">
              <FileText className="w-4 h-4 text-purple-600" />
              Statutory Deductions
            </h2>

            <div className="space-y-3 text-xs">
              <div className="flex justify-between py-2 border-b border-slate-100">
                <span className="text-slate-600">Employees' Provident Fund (EPF)</span>
                <span className="font-mono font-bold text-slate-800">
                  ₹{pf.toLocaleString('en-IN')}
                </span>
              </div>
              <div className="flex justify-between py-2 border-b border-slate-100">
                <span className="text-slate-600">Professional Tax (PT)</span>
                <span className="font-mono font-bold text-slate-800">
                  ₹{pt.toLocaleString('en-IN')}
                </span>
              </div>
              <div className="flex justify-between py-2 border-b border-slate-100">
                <span className="text-slate-600">Tax Deducted at Source (TDS)</span>
                <span className="font-mono font-bold text-slate-800">₹0</span>
              </div>
              <div className="flex justify-between pt-2 text-sm font-bold text-purple-700">
                <span>Total Deductions</span>
                <span className="font-mono">₹{deductions.toLocaleString('en-IN')}</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Monthly Payslips Table */}
      <div className="card">
        <h2 className="text-base font-bold text-slate-900 mb-4 flex items-center gap-2">
          <FileText className="w-4 h-4 text-blue-600" />
          Finalized Payslip Records
        </h2>

        {slips.length === 0 ? (
          <EmptyState
            icon={FileText}
            title="No Finalized Payslips Available"
            description="No finalized monthly payroll records have been generated in the database for your account. Payslips become accessible here once the monthly payroll cycle is executed by HR."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-200">
                <tr>
                  <th className="p-3">Period</th>
                  <th className="p-3">Disbursement Date</th>
                  <th className="p-3">Net Disbursed</th>
                  <th className="p-3">Status</th>
                  <th className="p-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {slips.map((s, i) => (
                  <tr key={s.slip_id || i} className="hover:bg-slate-50/60">
                    <td className="p-3 font-semibold text-slate-800">{s.month_name || s.year_month}</td>
                    <td className="p-3 font-mono text-slate-600">{s.payment_date || s.disbursement_date || '—'}</td>
                    <td className="p-3 font-mono font-bold text-emerald-700">
                      ₹{s.net_salary?.toLocaleString('en-IN') || '—'}
                    </td>
                    <td className="p-3">
                      <Badge status="active">{s.payment_status || 'Finalized'}</Badge>
                    </td>
                    <td className="p-3 text-right">
                      <button
                        onClick={() => handlePrintSlip(s.year_month)}
                        className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-blue-700 bg-blue-50 hover:bg-blue-100 rounded-lg transition"
                      >
                        <Download className="w-3.5 h-3.5" />
                        Download Slip
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default PayrollCenter;

