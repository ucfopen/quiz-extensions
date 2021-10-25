var selected_user_list = document.getElementById("selected_user_list");
var user_list = document.getElementById("user_list");
var user_list_div = document.getElementById("user_list_div");
var missing_alert = document.getElementById("missing_alert");
var modal_selected_user_list = document.getElementById("modal_selected_user_list");
var update_status = document.getElementById("update_status");
var results_div = document.getElementById("results");
var i = 0;
var update_interval_id = null;
var refresh_interval_id = null;

$("#user_list_div").on("click", ".user", function (e) {
	e.preventDefault();

	var user_id = $(this).attr("data-user-id")
	var is_duplicate = false;
	$("#selected_user_list").children().each(function (index, selected_user) {
		if ($(selected_user).attr("data-user-id") == user_id) {
			is_duplicate = true;
			return false;
		}
	});
	if (!is_duplicate) {
		var new_user_button = $(this).clone();
		$("#selected_user_list").append(new_user_button);
	}
	$(this).prop("disabled", true);
	checkIfEmpty();
});

$("#user_list_div").on("click", "#prev_user_page_button, #next_user_page_button", function (e) {
	ajaxFilter(
		$("#filter_users").val(),
		$(this).attr("data-page-number"),
		update_user_list
	);
});

$("#selected_user_list").on("click", ".user", function (e) {
	var selected_user = $(this);
	$("#user_list").children().each(function (index, user) {
		if ($(user).attr("data-user-id") == selected_user.attr("data-user-id")) {
			$(user).prop("disabled", false);
		}
	});
	selected_user.detach();
	checkIfEmpty();
});

$("#filter_users_button").on("click", function (e) {
	e.preventDefault();
	var query = $("#filter_users").val()
	ajaxFilter(query, curr_page_number, update_user_list);
});

$("#percent_select").on("change", function (e) {
	$("#modal_percent_added").html(getPercent());
});

$("#percent_input").on("input", function (e) {
	$("#modal_percent_added").html(getPercent())
});

$("#apply_now").on("click", function (e) {
	$("#percent_form").hide();
	$(update_status).show();
	$("#update").hide();
	$("#submit_button").hide();
	$("#close_button").prop("disabled", true);
	$("#close_x").hide();

	$.ajax({
		type: "POST",
		url: refresh_url
	})
		.done(function (data) {
			var refresh_job_url = data["refresh_job_url"];
			refresh_interval_id = setInterval(checkRefresh, 1000, refresh_job_url, true);
		})
		.fail(function (data) {
			// TODO: handle error case
		});
});

$("#go_button").on("click", function () {
	$("#modal_percent_added").html(getPercent())

	modal_selected_user_list.innerHTML = "";
	var num_selected_users = selected_user_list.children.length;

	if (num_selected_users === 0) {
		$("#submit_button").prop("disabled", true);
	}
	else {
		$("#submit_button").show();
		$("#submit_button").prop("disabled", false);
	}

	for (i = 0; i < num_selected_users; i++) {
		var user_id = selected_user_list.children[i].getAttribute("data-user-id");
		var user_name = $(selected_user_list.children[i]).text();

		var new_li = document.createElement("LI");
		new_li.setAttribute("data-user-id", user_id);
		new_li.innerHTML = user_name;

		modal_selected_user_list.appendChild(new_li);
	}
});

$("#clear_button").on("click", function (e) {
	clearSelectedStudents();
});

$("#submit_button").on("click", function (e) {
	$("#submit_button").prop("disabled", true);
	ajaxSend();
});

$("#go_modal").on("hidden.bs.modal", function (e) {
	$("#percent_form").show();
	$(update_status).hide();
	$(results_div).hide();
	$("#results_button").hide();
	resetBars();
});

$("#results_button").on("click", function (e) {
	e.preventDefault();

	$("#percent_form").hide();
	$(update_status).hide();
	$(results_div).show();
	$(this).hide();
});

function clearSelectedStudents() {
	var num_selected_users = selected_user_list.children.length;

	while (selected_user_list.children.length > 0) {
		selected_user_list.children[0].click();
	}
}

function clearAlerts() {
	var alerts_div = document.getElementById("alerts");
	while (alerts_div.children.length > 0) {
		alerts_div.removeChild(alerts_div.children[0]);
	}
}

function ajaxFilter(query, page, callback) {
	var xhttp = new XMLHttpRequest();

	user_list_div.innerHTML = "<div id=\"user_list\"><p>loading...</p></div>";

	xhttp.onreadystatechange = function () {
		if (xhttp.readyState == 4 && xhttp.status == 200) {
			user_list_div.innerHTML = xhttp.responseText;
		}
	};
	xhttp.onload = callback;
	xhttp.open("GET", filter_url + "?query=" + query + "&page=" + page, true);
	xhttp.send();
}

function getPercent() {
	var perc_input = $("#percent_input").val();
	if (perc_input !== null && perc_input !== "") {
		$("#percent_select").prop("disabled", true);
		if (perc_input >= 100) {
			return perc_input;
		}
		else {
			return $("#percent_select").val();
		}
	}
	else {
		$("#percent_select").prop("disabled", false);
		return $("#percent_select").val();
	}
}

function ajaxSend() {

	var selected_users = selected_user_list.children;

	var users_percent_obj = {
		user_ids: [],
		percent: getPercent()
	};

	for (i = 0; i < selected_users.length; i++) {
		var user_id = selected_users[i].getAttribute("data-user-id");
		users_percent_obj.user_ids.push(user_id);
	}
	$.ajax({
		type: "POST",
		url: update_url,
		headers: { "Content-Type": "application/json" },
		data: JSON.stringify(users_percent_obj)
	})
		.done(function (data) {
			$("#close_button").prop("disabled", true);
			$("#close_x").hide();

			var refresh_job_url = data["refresh_job_url"];
			var update_job_url = data["update_job_url"];

			refresh_interval_id = setInterval(checkRefresh, 1000, refresh_job_url, false);
			update_interval_id = setInterval(checkUpdate, 1000, update_job_url);
		})
		.fail(function (data) {
			$(update_status).html("<p>Encountered an error. Status " + data["status"] + "</p>");
		})
		.always(function (data) {
			$("#submit_button").hide();
			$("#percent_form").hide();
			$(update_status).show();
		});
}

function checkRefresh(refresh_job_url, refresh_only) {
	var refresh_div = $("#refresh");
	$.ajax({
		type: "GET",
		url: refresh_job_url
	})
		.done(function (data) {
			percent = data["percent"];
			refresh_div.find(".status-perc").html(percent.toString() + "%");
			var prog_bar = refresh_div.find(".progress-bar");
			prog_bar.attr("aria-valuenow", percent);
			prog_bar.attr("style", "width: " + percent.toString() + "%;");
			prog_bar.find("span").text(percent.toString() + "% Complete");

			if (data["status"] == "failed") {
				prog_bar.addClass("progress-bar-danger");
				prog_bar.removeClass("progress-bar-info");
				clearInterval(refresh_interval_id);
				clearInterval(update_interval_id);
				refresh_div.find(".status-msg").attr("style", "color: #f00;");
			}
			else if (data["status"] == "complete") {
				prog_bar.addClass("progress-bar-success");
				prog_bar.removeClass("progress-bar-info");
				clearInterval(refresh_interval_id);
				refresh_div.find(".status-msg").attr("style", "color: #000;");

				if (refresh_only === true) {
					resetModal();
				}
			}

			refresh_div.find(".status-msg").html(data["status_msg"]);
		})
		.fail(function (data) {
			var prog_bar = refresh_div.find(".progress-bar");

			prog_bar.addClass("progress-bar-danger");
			prog_bar.removeClass("progress-bar-info");
			clearInterval(refresh_interval_id);
			clearInterval(update_interval_id);

			refresh_div.find(".status-msg").html("<span style=\"color: #f00;\">Failed</span>");
			resetModal();
		});
}

function resetModal() {
	clearSelectedStudents();
	clearAlerts();
	$("#percent_input").val("");

	$("#close_button").prop("disabled", false);
	$("#close_x").show();
}

function checkUpdate(update_job_url) {
	var update_div = $("#update");
	$.ajax({
		type: "GET",
		url: update_job_url
	})
		.done(function (data) {

			// If there is no data yet, skip
			if ($.isEmptyObject(data)) {
				return;
			}

			percent = data["percent"];
			update_div.find(".status-perc").html(percent.toString() + "%");
			var prog_bar = update_div.find(".progress-bar");
			prog_bar.attr("aria-valuenow", percent);
			prog_bar.attr("style", "width: " + percent.toString() + "%;");
			prog_bar.find("span").text(percent.toString() + "% Complete");
			update_div.find(".status-msg").html(data["status_msg"]);

			if (data["status"] == "failed") {
				prog_bar.addClass("progress-bar-danger");
				prog_bar.removeClass("progress-bar-info");
				clearInterval(update_interval_id);
				update_div.find(".status-msg").attr("style", "color: #f00;");
			}
			else if (data["status"] == "complete") {
				prog_bar.addClass("progress-bar-success");
				prog_bar.removeClass("progress-bar-info");
				clearInterval(update_interval_id);
				update_div.find(".status-msg").attr("style", "color: #000;");

				updateResultTable(data["status_msg"], data["quiz_list"], data["unchanged_list"]);

				resetModal();
				$("#results_button").show();
			}
		})
		.fail(function (data) {
			percent = data["percent"];
			update_div.find(".status_perc").html(percent.toString() + "%");
			var prog_bar = update_div.find(".progress-bar");
			prog_bar.attr("aria-valuenow", percent);
			prog_bar.attr("style", "width: " + percent.toString() + "%;");
			prog_bar.find("span").text(percent.toString() + "% Complete");
			update_div.find(".status-msg").html(data["status_msg"]);

			prog_bar.addClass("progress-bar-danger");
			prog_bar.removeClass("progress-bar-info");
			clearInterval(update_interval_id);

			resetModal();
		});
}

function updateResultTable(message, quiz_list, unchanged_quiz_list) {
	results_div.innerHTML = "<p>" + message + "</p>";
	if (quiz_list.length > 0) {
		results_div.innerHTML += "<h4>Updated</h4>"
		var table_html = "<div id=\"table_div\"><table class=\"table table-striped table-condensed\"><thead><tr><th scope=\"col\">Quiz Title</th><th scope=\"col\">Minutes Extended</th></tr></thead><tbody>";
		for (var x in quiz_list) {
			table_html += "<tr><td>" +
				quiz_list[x]["title"] +
				"</td><td>" +
				quiz_list[x]["added_time"] +
				"</td></tr>";
		}
		table_html += "</tbody></table></div>";
		results_div.innerHTML += table_html;
	}
	else {
		results_div.innerHTML += "<p>No Quizzes were found.</p>"
	}

	if (unchanged_quiz_list.length > 0) {
		results_div.innerHTML += "<h4>Unchanged</h4>"
		var unchanged_table_html = "<div id=\"table_div\"><table class=\"table table-striped table-condensed\"><thead><tr><th scope=\"col\">Quiz Title</th></tr></thead><tbody>";
		for (var x in unchanged_quiz_list) {
			unchanged_table_html += "<tr><td>" +
				unchanged_quiz_list[x]["title"] +
				"</td></tr>";
		}
		unchanged_table_html += "</tbody></table></div>";
		results_div.innerHTML += unchanged_table_html;
	}
}

function update_user_list() {
	user_list = document.getElementById("user_list");
	selected_user_list = document.getElementById("selected_user_list");
	disableAlreadySelected();
	checkIfEmpty();
}

function resetBars() {
	$("#update, #refresh").each(function () {
		$(this).show();
		$(this).find(".status-perc").html("0%");
		var prog_bar = $(this).find(".progress-bar");
		prog_bar.attr("aria-valuenow", 0);
		prog_bar.attr("style", "width: 0%;");
		prog_bar.find("span").text("0% Complete");

		prog_bar.addClass("progress-bar-info");
		prog_bar.removeClass("progress-bar-danger");
		prog_bar.removeClass("progress-bar-success");

		$(this).find(".status-msg").html("Not Started");
	});
}

function disableAlreadySelected() {
	// grays out users who are already selected from search results.
	var selected_user_ids = [];
	var users = user_list.children;
	var selected_users = selected_user_list.children;

	for (i = 0; i < selected_users.length; i++) {
		selected_user_ids.push(selected_users[i].getAttribute("data-user-id"));
	}

	for (i = 0; i < users.length; i++) {
		var user_id = users[i].getAttribute("data-user-id");
		if (selected_user_ids.indexOf(user_id) > -1) {
			user_list.children[i].setAttribute("disabled", true);
		}
	}
}

function checkIfEmpty() {
	var user_list_children = user_list.getElementsByClassName("user");

	if (user_list_children.length <= 0) {
		var p = document.createElement("p");
		p.className = "no-matching";
		p.innerHTML = "No matching students found.";
		user_list.appendChild(p);
	}
	else {
		no_matching_warnings = user_list.getElementsByClassName("no-matching");
		for (i = 0; i < no_matching_warnings.length; i++) {
			user_list.removeChild(no_matching_warnings[i]);
		}
	}
}

function ajax_check_missing_and_stale_quizzes(course_id) {
	var xhttp = new XMLHttpRequest();

	xhttp.onreadystatechange = function () {
		if (xhttp.readyState == 4 && xhttp.status == 200) {
			var response = JSON.parse(xhttp.responseText);

			if (response) {
				missing_alert.style.display = "";
				resizeFrame();
			}
			else {
				missing_alert.style.display = "none";
				resizeFrame();
			}
		}
	};
	xhttp.open("GET", missing_and_stale_quizzes_url, true);
	xhttp.send();
}

function load_func() {
	// load initial user list
	ajaxFilter("", 1, update_user_list);

	// check for missing quizzes
	ajax_check_missing_and_stale_quizzes(course_id);
}

window.onload = load_func;
