// Native .NET Framework launcher. The Python service and all research stay local.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

[assembly: AssemblyTitle("Hypothesis Lab")]
[assembly: AssemblyDescription("Local quantitative research workbench")]
[assembly: AssemblyCompany("Hypothesis Lab contributors")]
[assembly: AssemblyProduct("Hypothesis Lab")]
[assembly: AssemblyVersion("0.2.0.0")]

internal static class Program
{
    internal static string Folder = AppDomain.CurrentDomain.BaseDirectory;

    internal static ProcessStartInfo Python(string arguments)
    {
        ProcessStartInfo start = new ProcessStartInfo();
        start.FileName = Path.Combine(Folder, "runtime", "python.exe");
        start.Arguments = "-B -u " + arguments;
        start.WorkingDirectory = Folder;
        start.UseShellExecute = false;
        start.CreateNoWindow = true;
        start.RedirectStandardOutput = true;
        start.RedirectStandardError = true;
        start.EnvironmentVariables["HYPOTHESIS_LAB_PORTABLE"] = "1";
        return start;
    }

    [STAThread]
    private static int Main(string[] arguments)
    {
        bool smoke = Array.IndexOf(arguments, "--smoke-test") >= 0;
        if (smoke)
        {
            try
            {
                using (Process process = new Process())
                {
                    process.StartInfo = Python("-m hypothesis_lab.desktop_smoke");
                    process.OutputDataReceived += delegate(object sender, DataReceivedEventArgs e)
                    { if (e.Data != null) Console.Out.WriteLine(e.Data); };
                    process.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs e)
                    { if (e.Data != null) Console.Error.WriteLine(e.Data); };
                    process.Start();
                    process.BeginOutputReadLine();
                    process.BeginErrorReadLine();
                    if (!process.WaitForExit(90000))
                    {
                        process.Kill();
                        process.WaitForExit();
                        return 2;
                    }
                    process.WaitForExit();
                    return process.ExitCode;
                }
            }
            catch (Exception error)
            {
                Console.Error.WriteLine("Desktop smoke could not start: " + error.Message);
                return 1;
            }
        }
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new Launcher(Array.IndexOf(arguments, "--no-browser") >= 0));
        return 0;
    }
}

internal sealed class Launcher : Form
{
    private readonly bool noBrowser;
    private readonly Label status = new Label();
    private readonly Button open = new Button();
    private readonly Button quit = new Button();
    private Process child;
    private string address;
    private bool stopping;
    private bool closingAllowed;
    private readonly System.Windows.Forms.Timer readyTimeout = new System.Windows.Forms.Timer();

    internal Launcher(bool noBrowser)
    {
        this.noBrowser = noBrowser;
        Text = "Hypothesis Lab";
        ClientSize = new Size(490, 250);
        StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        BackColor = Color.FromArgb(246, 246, 238);
        Font = new Font("Segoe UI", 10);
        Label title = new Label();
        title.Text = "Hypothesis Lab";
        title.Font = new Font("Segoe UI", 22, FontStyle.Regular);
        title.ForeColor = Color.FromArgb(29, 48, 40);
        title.SetBounds(28, 24, 420, 42);
        Label subtitle = new Label();
        subtitle.Text = "Your research runs privately on this computer.";
        subtitle.SetBounds(31, 76, 425, 25);
        status.Text = "Starting the workbench...";
        status.ForeColor = Color.FromArgb(83, 104, 78);
        status.SetBounds(31, 112, 425, 46);
        open.Text = "Open app";
        open.SetBounds(31, 180, 190, 40);
        open.Enabled = false;
        open.Click += delegate { OpenBrowser(); };
        quit.Text = "Quit";
        quit.SetBounds(239, 180, 190, 40);
        quit.Click += delegate { StopAndClose(); };
        Controls.AddRange(new Control[] { title, subtitle, status, open, quit });
        Shown += delegate { StartChild(); };
        FormClosing += delegate(object sender, FormClosingEventArgs e)
        {
            if (!closingAllowed && ChildRunning())
            {
                e.Cancel = true;
                StopAndClose();
            }
        };
        readyTimeout.Interval = 30000;
        readyTimeout.Tick += delegate
        {
            readyTimeout.Stop();
            if (address == null && ChildRunning())
            {
                status.Text = "The app is taking longer than expected. Quit and try again.";
            }
        };
    }

    private void OnUI(Action action)
    {
        if (IsDisposed || !IsHandleCreated) return;
        try { BeginInvoke(action); }
        catch (InvalidOperationException) { }
    }

    private bool ChildRunning()
    {
        try { return child != null && !child.HasExited; }
        catch (InvalidOperationException) { return false; }
    }

    private void StartChild()
    {
        try
        {
            child = new Process();
            child.StartInfo = Program.Python("-m hypothesis_lab --port 0 --no-browser");
            child.EnableRaisingEvents = true;
            child.OutputDataReceived += delegate(object sender, DataReceivedEventArgs e)
            {
                if (e.Data == null) return;
                Match match = Regex.Match(e.Data, @"http://127\.0\.0\.1:[0-9]+(?:\s|$)");
                if (match.Success) OnUI(delegate { Ready(match.Value.Trim()); });
            };
            child.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs e)
            { /* Research inputs and credential-bearing URLs are never written to logs. */ };
            child.Exited += delegate
            {
                OnUI(delegate
                {
                    readyTimeout.Stop();
                    if (stopping || child.ExitCode == 0)
                    {
                        closingAllowed = true;
                        Close();
                    }
                    else
                    {
                        status.Text = "The app stopped. Extract the whole ZIP to a folder and try again.";
                        open.Enabled = false;
                    }
                });
            };
            child.Start();
            child.BeginOutputReadLine();
            child.BeginErrorReadLine();
            readyTimeout.Start();
        }
        catch (Exception)
        {
            status.Text = "Could not start. Extract the whole ZIP to a folder and try again.";
            open.Enabled = false;
        }
    }

    private void Ready(string value)
    {
        if (address != null || stopping) return;
        Uri parsed;
        if (!Uri.TryCreate(value, UriKind.Absolute, out parsed)
            || parsed.Scheme != "http" || parsed.Host != "127.0.0.1" || parsed.Port < 1) return;
        address = value;
        readyTimeout.Stop();
        status.Text = "Running locally. Keep this window open while you research.";
        open.Enabled = true;
        if (!noBrowser) OpenBrowser();
    }

    private void OpenBrowser()
    {
        if (address == null || !ChildRunning()) return;
        try { Process.Start(new ProcessStartInfo(address) { UseShellExecute = true }); }
        catch (Exception) { status.Text = "Open your browser and visit " + address; }
    }

    private string Request(string path, string token)
    {
        HttpWebRequest request = (HttpWebRequest)WebRequest.Create(address + path);
        request.Proxy = null;
        request.Timeout = 2000;
        request.ReadWriteTimeout = 2000;
        if (token != null)
        {
            byte[] body = Encoding.UTF8.GetBytes("{}");
            request.Method = "POST";
            request.ContentType = "application/json";
            request.Headers["Origin"] = address;
            request.Headers["X-Lab-Token"] = token;
            request.ContentLength = body.Length;
            using (Stream stream = request.GetRequestStream()) stream.Write(body, 0, body.Length);
        }
        using (WebResponse response = request.GetResponse())
        using (StreamReader reader = new StreamReader(response.GetResponseStream()))
            return reader.ReadToEnd();
    }

    private void StopAndClose()
    {
        if (stopping) return;
        stopping = true;
        readyTimeout.Stop();
        open.Enabled = false;
        quit.Enabled = false;
        status.Text = "Stopping the local app...";
        ThreadPool.QueueUserWorkItem(delegate
        {
            try
            {
                if (address != null && ChildRunning())
                {
                    Dictionary<string, object> bootstrap = new JavaScriptSerializer()
                        .Deserialize<Dictionary<string, object>>(Request("/api/bootstrap", null));
                    object token;
                    if (bootstrap.TryGetValue("token", out token) && token is string)
                        Request("/api/shutdown", (string)token);
                }
            }
            catch (Exception) { /* Close remains available when the local service failed. */ }
            try
            {
                if (ChildRunning() && !child.WaitForExit(5000)) child.Kill();
            }
            catch (InvalidOperationException) { }
            OnUI(delegate { closingAllowed = true; Close(); });
        });
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing) readyTimeout.Dispose();
        base.Dispose(disposing);
    }
}
