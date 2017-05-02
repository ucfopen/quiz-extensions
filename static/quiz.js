var filter_button = document.getElementById("filter_users_button");
var filter_text = document.getElementById("filter_users");
var selected_user_list = document.getElementById("selected_user_list");
var user_list = document.getElementById("user_list");
var user_list_div = document.getElementById("user_list_div");
var percent_added_span = document.getElementById("modal_percent_added");
var missing_alert = document.getElementById('missing_alert');
var modal_selected_user_list = document.getElementById("modal_selected_user_list");
var percent_form = document.getElementById("percent_form");
var percent_select = document.getElementById("percent_select");
var percent_input = document.getElementById("percent_input");
var go_button = document.getElementById("go_button");
var clear_button = document.getElementById("clear_button");
var submit_button = document.getElementById("submit_button");
var update_status = document.getElementById("update_status");
var results_div = document.getElementById("results");
var close_button = document.getElementById("close_button");
var results_button = document.getElementById("results_button");
var close_x = document.getElementById("close_x");
var i = 0;
var update_interval_id = null;
var refresh_interval_id = null;

user_list_div.addEventListener('click', function(e) {
	e.preventDefault();

	if (e.target.tagName.toLowerCase() == "button" && e.target.classList.contains("user")) {
		var user_button = e.target;

		var user_id = user_button.getAttribute("data-user-id");

		var is_duplicate = false;
		for (i=0; i<selected_user_list.children.length; i++) {
			var selected_user = selected_user_list.children[i];
			if (selected_user.getAttribute("data-user-id") == user_id) {
				is_duplicate = true;
				break;
			}
		}
		if (!is_duplicate) {
			var new_user_button = user_button.cloneNode(true);
			selected_user_list.appendChild(new_user_button);
		}

		user_button.disabled = true;
		checkIfEmpty();
	}
	else if (e.target.id == "prev_user_page_button" || e.target.id == "next_user_page_button") {
		var query = filter_text.value;
		var page_number = e.target.getAttribute("data-page-number");

		ajaxFilter(query, page_number, update_user_list);
	}
});

selected_user_list.addEventListener('click', function(e) {
	if (e.target.tagName.toLowerCase() == "button" && e.target.classList.contains("user")) {
		var selected_user_li = e.target;
		var selected_user_id = selected_user_li.getAttribute("data-user-id");

		for (i=0; i<user_list.children.length; i++) {
			var user = user_list.children[i];
			if (user.getAttribute("data-user-id") == selected_user_id) {
				user.disabled = false;
			}
		}

		selected_user_list.removeChild(selected_user_li);

		checkIfEmpty();
	}
});

filter_button.addEventListener('click', function(e) {
	e.preventDefault();
	var query = filter_text.value;
	ajaxFilter(query, curr_page_number, update_user_list);
});

percent_select.addEventListener('change', function(e) {
	percent_added_span.innerHTML = getPercent();
});

percent_input.addEventListener('input', function(e) {
	percent_added_span.innerHTML = getPercent();
});

$('#apply_now').on('click', function(e) {
	$(percent_form).hide();
	$(update_status).show();
	$('#update').hide();
	$('#submit_button').hide();
	$('#close_button').prop("disabled", true);
	$(close_x).hide();

	$.ajax({
		type: "POST",
		url: refresh_url
	})
	.done(function(data) {
		var refresh_job_url = data['refresh_job_url'];
		refresh_interval_id = setInterval(checkRefresh, 1000, refresh_job_url, true);
	})
	.fail(function(data) {
		// TODO: handle error case
	});
});

go_button.addEventListener('click', function(e) {
	percent_added_span.innerHTML = getPercent();

	modal_selected_user_list.innerHTML = "";
	var num_selected_users = selected_user_list.children.length;

	if (num_selected_users === 0) {
		submit_button.disabled = true;
	}
	else {
		submit_button.style.display = "";
		submit_button.disabled = false;
	}

	for (i=0; i<num_selected_users; i++) {
		var user_id = selected_user_list.children[i].getAttribute("data-user-id");
		var user_name = $(selected_user_list.children[i]).text();

		var new_li = document.createElement("LI");
		new_li.setAttribute("data-user-id", user_id);
		new_li.innerHTML = user_name;

		modal_selected_user_list.appendChild(new_li);
	}
});

clear_button.addEventListener('click', function(e) {
	clearSelectedStudents();
});

submit_button.addEventListener('click', function(e) {
	$(submit_button).prop('disabled', true);
	ajaxSend();
});

$("#go_modal").on('hidden.bs.modal', function(e) {
	$(percent_form).show();
	$(update_status).hide();
	$(results_div).hide();
	$(results_button).hide();
	resetBars();
});

$('#results_button').on('click', function(e) {
	e.preventDefault();

	$(percent_form).hide();
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
	var alerts_div = document.getElementById('alerts');
	while(alerts_div.children.length > 0) {
		alerts_div.removeChild(alerts_div.children[0]);
	}
}

function ajaxFilter(query, page, callback) {
	var xhttp = new XMLHttpRequest();

	user_list_div.innerHTML = "<div id=\"user_list\"><p>loading...</p></div>";

	xhttp.onreadystatechange = function() {
		if (xhttp.readyState == 4 && xhttp.status == 200) {
			user_list_div.innerHTML = xhttp.responseText;
		}
	};
	xhttp.onload = callback;
	xhttp.open("GET", filter_url+"?query=" + query + "&page=" + page, true);
	xhttp.send();
}

function getPercent() {
	if (percent_input.value !== null && percent_input.value !== "") {
		percent_select.disabled = true;
		if (percent_input.value >= 100) {
			return percent_input.value;
		}
		else {
			return percent_select.value;
		}
	}
	else {
		percent_select.disabled = false;
		return percent_select.value;
	}
}

function ajaxSend() {

	var selected_users = selected_user_list.children;

	var users_percent_obj = {
		user_ids: [],
		percent: getPercent()
	};

	for (i=0; i<selected_users.length; i++) {
		var user_id = selected_users[i].getAttribute("data-user-id");
		users_percent_obj.user_ids.push(user_id);
	}
	$.ajax({
		type: "POST",
		url: update_url,
		headers: {"Content-Type": "application/json"},
		data: JSON.stringify(users_percent_obj)
	})
	.done(function(data) {
		close_button.disabled = true;
		close_x.style.display = "none";

		var refresh_job_url = data['refresh_job_url'];
		var update_job_url = data['update_job_url'];

		refresh_interval_id = setInterval(checkRefresh, 1000, refresh_job_url, false);
		update_interval_id = setInterval(checkUpdate, 1000, update_job_url);
	})
	.fail(function(data) {
		$(update_status).html("<p>Encountered an error. Status "+ data['status'] + "</p>");
	})
	.always(function(data) {
		$(submit_button).hide();
		$(percent_form).hide();
		$(update_status).show();
	});
}

function checkRefresh(refresh_job_url, refresh_only) {
	var refresh_div = $('#refresh');
	$.ajax({
		type: "GET",
		url: refresh_job_url
	})
	.done(function(data) {
		percent = data['percent'];
		refresh_div.find(".status-perc").html(percent.toString() + '%');
		var prog_bar = refresh_div.find(".progress-bar");
		prog_bar.attr('aria-valuenow', percent);
		prog_bar.attr('style', 'width: ' + percent.toString() + '%;');
		prog_bar.find('span').text(percent.toString() + '% Complete');
		
		if (data['status'] == "failed") {
			prog_bar.addClass('progress-bar-danger');
			prog_bar.removeClass('progress-bar-info');
			clearInterval(refresh_interval_id);
		}
		else if (data['status'] == "complete") {
			prog_bar.addClass('progress-bar-success');
			prog_bar.removeClass('progress-bar-info');
			clearInterval(refresh_interval_id);

			if (refresh_only === true) {
				resetModal();
			}
		}

		refresh_div.find(".status-msg").html(data['status_msg']);
	});
}

function resetModal() {
	clearSelectedStudents();
	clearAlerts();
	percent_input.value = "";

	$(close_button).prop('disabled', false);
	$(close_x).show();
}

function checkUpdate(update_job_url) {
	var update_div = $('#update');
	$.ajax({
		type: "GET",
		url: update_job_url
	})
	.done(function(data) {

		// If there is no data yet, skip
		if ($.isEmptyObject(data)) {
			return;
		}

		percent = data['percent'];
		update_div.find(".status-perc").html(percent.toString() + '%');
		var prog_bar = update_div.find(".progress-bar");
		prog_bar.attr('aria-valuenow', percent);
		prog_bar.attr('style', 'width: ' + percent.toString() + '%;');
		prog_bar.find('span').text(percent.toString() + '% Complete');
		update_div.find(".status-msg").html(data['status_msg']);

		if (data['status'] == "failed") {
			prog_bar.addClass('progress-bar-danger');
			prog_bar.removeClass('progress-bar-info');
			clearInterval(update_interval_id);
		}
		else if (data['status'] == "complete") {
			prog_bar.addClass('progress-bar-success');
			prog_bar.removeClass('progress-bar-info');
			clearInterval(update_interval_id);

			updateResultTable(data['status_msg'], data['quiz_list'], data['unchanged_list']);

			resetModal();
			$(results_button).show();
		}
	});
}

function updateResultTable(message, quiz_list, unchanged_quiz_list) {
	results_div.innerHTML = "<p>"+ message + "</p>";
	if (quiz_list.length > 0) {
		results_div.innerHTML += "<h4>Updated</h4>"
		var table_html = "<div id='table_div'><table class='table table-striped table-condensed'><thead><tr><th scope='col'>Quiz Title</th><th scope='col'>Minutes Extended</th></tr></thead><tbody>";
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
		var unchanged_table_html = "<div id='table_div'><table class='table table-striped table-condensed'><thead><tr><th scope='col'>Quiz Title</th></tr></thead><tbody>";
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
	$('#update, #refresh').each(function() {
		$(this).show();
		$(this).find(".status-perc").html('0%');
		var prog_bar = $(this).find(".progress-bar");
		prog_bar.attr('aria-valuenow', 0);
		prog_bar.attr('style', 'width: 0%;');
		prog_bar.find('span').text('0% Complete');

		prog_bar.addClass('progress-bar-info');
		prog_bar.removeClass('progress-bar-danger');
		prog_bar.removeClass('progress-bar-success');

		$(this).find(".status-msg").html("Not Started");
	});
}

function disableAlreadySelected() {
	// grays out users who are already selected from search results.
	var selected_user_ids = [];
	var users = user_list.children;
	var selected_users = selected_user_list.children;

	for (i=0; i<selected_users.length; i++) {
		selected_user_ids.push(selected_users[i].getAttribute("data-user-id"));
	}

	for (i=0; i<users.length; i++) {
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
		for (i=0; i<no_matching_warnings.length; i++) {
			user_list.removeChild(no_matching_warnings[i]);
		}
	}
}

function ajax_check_missing_quizzes(course_id) {
	var xhttp = new XMLHttpRequest();

	xhttp.onreadystatechange = function() {
		if (xhttp.readyState == 4 && xhttp.status == 200) {
			var response = JSON.parse(xhttp.responseText);

			if (response) {
				missing_alert.style.display = "";
			}
			else {
				missing_alert.style.display = "none";
			}
		}
	};
	xhttp.open("GET", missing_quizzes_url, true);
	xhttp.send();
}

function load_func() {
	// load initial user list
	ajaxFilter('', 1, update_user_list);

	// check for missing quizzes
	ajax_check_missing_quizzes(course_id);
}

window.onload = load_func;
